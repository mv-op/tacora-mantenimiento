"""Consultas del árbol para las pantallas y creación de nodos por los operadores."""

from collections import Counter

from django.core.exceptions import ValidationError
from django.db import transaction
from rapidfuzz import fuzz, process

from .models import CoordinadorMaquina, EstadoCuraduria, Nivel, NodoActivo, Origen
from .normalizar import normalizar

SIMILITUD_MINIMA = 60  # % de rapidfuzz para sugerir un nodo existente


def hijos_activos(padre):
    """Hijos activos de un nodo, o las máquinas si `padre` es None."""
    return NodoActivo.objects.filter(padre=padre, is_active=True).order_by("nombre")


def nivel_de_hijos(padre):
    """Nivel que tendrían los hijos de `padre`, o None si ya es un componente."""
    if padre is None:
        return Nivel.MAQUINA
    return Nivel(padre.nivel + 1) if padre.nivel < Nivel.COMPONENTE else None


def sugerencias(padre, texto, limite=5):
    """Nodos hermanos con nombre parecido a `texto` (búsqueda difusa)."""
    buscado = normalizar(texto)
    if len(buscado) < 2:
        return []
    candidatos = {n.pk: n for n in hijos_activos(padre)}
    resultados = process.extract(
        buscado, {pk: n.nombre_normalizado for pk, n in candidatos.items()},
        scorer=fuzz.WRatio, limit=limite, score_cutoff=SIMILITUD_MINIMA,
    )
    return [candidatos[pk] for _, _, pk in resultados]


def nombres_usados(padre, texto="", limite=8):
    """Nombres del mismo nivel usados en otras partes del árbol, para escribirlos igual.

    Sin texto, devuelve los más usados. Devuelve [(nombre, veces)]; omite los que ya existen bajo `padre`.
    """
    nivel = nivel_de_hijos(padre)
    if nivel is None:
        return []
    aqui = set(hijos_activos(padre).values_list("nombre_normalizado", flat=True))
    escrituras = {}  # nombre normalizado → Counter de cómo se escribió
    for normalizado, nombre in NodoActivo.objects.filter(nivel=nivel, is_active=True).values_list(
            "nombre_normalizado", "nombre"):
        if normalizado not in aqui:
            escrituras.setdefault(normalizado, Counter())[nombre] += 1
    # Para cada nombre se muestra la escritura más común.
    opciones = {norm: (veces.most_common(1)[0][0], sum(veces.values())) for norm, veces in escrituras.items()}

    buscado = normalizar(texto)
    if not buscado:
        return sorted(opciones.values(), key=lambda o: (-o[1], o[0]))[:limite]
    resultados = process.extract(buscado, {norm: norm for norm in opciones}, scorer=fuzz.WRatio,
                                 limit=limite, score_cutoff=SIMILITUD_MINIMA)
    return [opciones[norm] for _, _, norm in resultados]


def crear_nodo_operador(padre, nombre, usuario):
    """Crea un nodo propuesto por un operador (curaduría pendiente).

    Si ya existe un hermano con el mismo nombre normalizado, devuelve ese. Devuelve (nodo, creado).
    """
    nivel = nivel_de_hijos(padre)
    if nivel is None:
        raise ValidationError("Un componente no puede tener hijos.")
    nombre = " ".join(nombre.split())
    if not normalizar(nombre):
        raise ValidationError("Escriba un nombre con letras o números.")
    existente = hijos_activos(padre).filter(nombre_normalizado=normalizar(nombre)).first()
    if existente:
        return existente, False
    nodo = NodoActivo(nombre=nombre, nivel=nivel, padre=padre, origen=Origen.OPERADOR,
                      estado_curaduria=EstadoCuraduria.PENDIENTE, creado_por=usuario)
    nodo.full_clean()
    nodo._change_reason = "Creado por operador desde la app"
    nodo.save()
    # Fase 6: notificar() al administrador (nodo pendiente de curaduría).
    return nodo, True


@transaction.atomic
def fusionar(correcto, duplicado, resumen=None):
    """Pasa todo lo del duplicado al nodo correcto y desactiva el duplicado (con `fusionado_en`).

    Mueve tickets, hijos, coordinadores y hallazgos. Si ambos tienen un hijo con el mismo nombre,
    esos hijos también se fusionan. Devuelve un resumen con lo que se movió.
    """
    if resumen is None:
        resumen = {"tickets": 0, "hijos_movidos": 0, "hijos_fusionados": 0}
    if correcto.pk == duplicado.pk:
        raise ValidationError("Un nodo no se puede fusionar consigo mismo.")
    if correcto.nivel != duplicado.nivel:
        raise ValidationError("Solo se fusionan nodos del mismo nivel.")
    if not (correcto.is_active and duplicado.is_active):
        raise ValidationError("Solo se fusionan nodos activos.")

    motivo = f"Fusión: #{duplicado.pk} «{duplicado.nombre}» → #{correcto.pk} «{correcto.nombre}»"

    for ticket in duplicado.tickets.all():
        ticket.nodo = correcto
        ticket._change_reason = motivo
        ticket.save(update_fields=["nodo"])
        resumen["tickets"] += 1

    hijos_del_correcto = {h.nombre_normalizado: h for h in hijos_activos(correcto)}
    for hijo in list(hijos_activos(duplicado)):
        gemelo = hijos_del_correcto.get(hijo.nombre_normalizado)
        if gemelo:
            fusionar(gemelo, hijo, resumen)
            resumen["hijos_fusionados"] += 1
        else:
            hijo.padre = correcto
            hijo._change_reason = motivo
            hijo.save()
            resumen["hijos_movidos"] += 1

    for asignacion in CoordinadorMaquina.objects.filter(maquina=duplicado):
        if CoordinadorMaquina.objects.filter(maquina=correcto, coordinador=asignacion.coordinador_id).exists():
            asignacion.delete()
        else:
            asignacion.maquina = correcto
            asignacion.save()
    duplicado.hallazgos.update(nodo=correcto)

    duplicado.is_active = False
    duplicado.fusionado_en = correcto
    duplicado._change_reason = motivo
    duplicado.save()
    return resumen
