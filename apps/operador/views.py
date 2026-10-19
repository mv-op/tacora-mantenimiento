"""Pantallas del operador: elegir el activo, describir la falla y ver sus reportes.

Las páginas se navegan con hx-boost: cada vista devuelve la página completa y HTMX solo reemplaza #paso.
"""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.activos import servicios as activos
from apps.activos.models import Nivel, NodoActivo
from apps.tickets.models import Criticidad, Ticket
from apps.tickets.servicios import MIN_CARACTERES_DESCRIPCION, crear_ticket

AYUDA_CRITICIDAD = {
    Criticidad.CRITICA: "Detiene la producción o es un riesgo de seguridad.",
    Criticidad.URGENTE: "Afecta la producción, pero el equipo sigue funcionando.",
    Criticidad.IMPORTANTE: "No afecta la producción ahora; se puede programar.",
}


def _nodo_activo(nodo_id):
    return get_object_or_404(NodoActivo, pk=nodo_id, is_active=True)


def _padre_de_peticion(request):
    padre_id = request.GET.get("padre") or request.POST.get("padre")
    return _nodo_activo(padre_id) if padre_id and str(padre_id).isdigit() else None


def _pasos(nivel_actual):
    """Barra de 5 pasos: los niveles ya elegidos, el actual y los que faltan."""
    return [(nivel, "hecho" if nivel < nivel_actual else "actual" if nivel == nivel_actual else "pendiente")
            for nivel in Nivel]


@login_required
def mosaico(request, nodo_id=None):
    nodo = _nodo_activo(nodo_id) if nodo_id else None
    nivel_hijos = activos.nivel_de_hijos(nodo)
    return render(request, "operador/mosaico.html", {
        "nodo": nodo,
        "ancestros": nodo.ancestros if nodo else [],
        "hijos": activos.hijos_activos(nodo),
        "nivel_hijos": nivel_hijos,
        "pasos": _pasos(nivel_hijos or nodo.nivel),
    })


@login_required
def crear_nodo(request):
    padre = _padre_de_peticion(request)
    nivel = activos.nivel_de_hijos(padre)
    if nivel is None:
        return redirect("reportar_nodo", padre.pk)
    error, nombre = None, ""
    if request.method == "POST":
        nombre = request.POST.get("nombre", "")
        try:
            nodo, creado = activos.crear_nodo_operador(padre, nombre, request.user)
        except ValidationError as e:
            error = " ".join(e.messages)
        else:
            if creado:
                messages.success(request, f"Se agregó «{nodo.nombre}». El administrador lo revisará.")
            else:
                messages.info(request, f"«{nodo.nombre}» ya existía; se usó ese.")
            return redirect("reportar_nodo", nodo.pk)
    return render(request, "operador/crear_nodo.html", {
        "padre": padre, "ancestros": padre.ancestros if padre else [], "nivel": nivel, "pasos": _pasos(nivel),
        "error": error, "nombre": nombre,
        "sugerencias": activos.sugerencias(padre, nombre), "usados": activos.nombres_usados(padre, nombre),
    })


@login_required
def sugerencias(request):
    padre = _padre_de_peticion(request)
    texto = request.GET.get("nombre", "")
    return render(request, "operador/_sugerencias.html", {
        "sugerencias": activos.sugerencias(padre, texto),
        "usados": activos.nombres_usados(padre, texto),
        "nivel": activos.nivel_de_hijos(padre),
    })


@login_required
def describir(request, nodo_id):
    nodo = _nodo_activo(nodo_id)
    criticidades = [(valor, etiqueta, AYUDA_CRITICIDAD[valor]) for valor, etiqueta in Criticidad.choices]
    return render(request, "operador/describir.html", {
        "nodo": nodo, "ancestros": nodo.ancestros, "criticidades": criticidades,
        "minimo": MIN_CARACTERES_DESCRIPCION,
    })


@require_POST
@login_required
def enviar_reporte(request):
    """Recibe el reporte desde el navegador (también los reenvíos sin conexión). Responde JSON."""
    try:
        uuid_cliente = uuid.UUID(request.POST.get("uuid", ""))
    except ValueError:
        return JsonResponse({"errores": ["El reporte no tiene un código válido. Vuelva a empezarlo."]}, status=400)

    # Un reenvío del mismo reporte devuelve el ticket ya creado, sin volver a validar.
    existente = Ticket.objects.filter(uuid_cliente=uuid_cliente, reportado_por=request.user).first()
    if existente:
        return JsonResponse({"ticket": existente.pk, "creado": False, "url": reverse("mi_reporte", args=[existente.pk])})

    errores = []
    nodo_id = request.POST.get("nodo", "")
    nodo = NodoActivo.objects.filter(pk=nodo_id, is_active=True).first() if nodo_id.isdigit() else None
    if nodo is None:
        errores.append("El activo elegido ya no está disponible. Elija otro.")
    descripcion = request.POST.get("descripcion", "")
    if len(descripcion.strip()) < MIN_CARACTERES_DESCRIPCION:
        errores.append(f"Describa la falla con al menos {MIN_CARACTERES_DESCRIPCION} caracteres.")
    criticidad = request.POST.get("criticidad", "")
    if criticidad not in Criticidad.values:
        errores.append("Elija la criticidad.")
    if errores:
        return JsonResponse({"errores": errores}, status=400)

    # La descripción se guarda tal como la escribió el operador.
    ticket, creado = crear_ticket(uuid_cliente=uuid_cliente, nodo=nodo, descripcion=descripcion,
                                  criticidad=criticidad, reportado_por=request.user)
    return JsonResponse({"ticket": ticket.pk, "creado": creado, "url": reverse("mi_reporte", args=[ticket.pk])},
                        status=201 if creado else 200)


@login_required
def mis_reportes(request):
    tickets = (Ticket.objects.filter(reportado_por=request.user)
               .select_related("nodo", "tecnico").order_by("-reportado_en")[:50])
    return render(request, "operador/mis_reportes.html", {"tickets": tickets})


@login_required
def mi_reporte(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("nodo", "tecnico"), pk=pk, reportado_por=request.user)
    return render(request, "operador/mi_reporte.html", {
        "ticket": ticket, "eventos": ticket.eventos.select_related("actor"),
        "recien_enviado": request.GET.get("enviado") == "1",
    })
