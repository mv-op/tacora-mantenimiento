"""Funciones de servicio de tickets. Las vistas nunca cambian el estado directamente.

Todo cambio de estado pasa por `transicionar()`, que valida la transición y crea el EventoTicket.
"""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.activos.models import CoordinadorMaquina
from apps.usuarios.models import Rol

from .models import CierreTecnico, ContraReporte, Estado, EventoTicket, ReglaSLA, Ticket, TipoEvento

MIN_CARACTERES_DESCRIPCION = 20
MIN_CARACTERES_CIERRE = 20
MIN_CARACTERES_MOTIVO = 10


class TransicionInvalida(Exception):
    """El cambio de estado no está permitido; el mensaje se muestra tal cual al usuario."""


@dataclass(frozen=True)
class Regla:
    desde: frozenset
    hacia: str | None  # None: el estado no cambia (reasignar)
    roles: frozenset


# Transiciones permitidas: (desde qué estados, a cuál, quién la hace).
TRANSICIONES = {
    TipoEvento.ASIGNAR: Regla(frozenset({Estado.REPORTADO}), Estado.ASIGNADO, frozenset({Rol.COORDINADOR})),
    TipoEvento.REASIGNAR: Regla(frozenset({Estado.ASIGNADO, Estado.EN_PAUSA}), None, frozenset({Rol.COORDINADOR})),
    TipoEvento.INICIAR: Regla(frozenset({Estado.ASIGNADO}), Estado.EN_PROCESO, frozenset({Rol.TECNICO})),
    TipoEvento.PAUSAR: Regla(frozenset({Estado.EN_PROCESO}), Estado.EN_PAUSA, frozenset({Rol.TECNICO})),
    TipoEvento.REANUDAR: Regla(frozenset({Estado.EN_PAUSA}), Estado.EN_PROCESO,
                               frozenset({Rol.COORDINADOR, Rol.TECNICO})),
    TipoEvento.RESOLVER: Regla(frozenset({Estado.EN_PROCESO}), Estado.RESUELTO, frozenset({Rol.TECNICO})),
    TipoEvento.VALIDAR: Regla(frozenset({Estado.RESUELTO}), Estado.CERRADO, frozenset({Rol.COORDINADOR})),
    TipoEvento.RECHAZAR: Regla(frozenset({Estado.RESUELTO}), Estado.EN_PROCESO, frozenset({Rol.COORDINADOR})),
    TipoEvento.ANULAR: Regla(frozenset({Estado.REPORTADO}), Estado.ANULADO, frozenset({Rol.COORDINADOR})),
}

# Estados en los que el ticket está en manos de un técnico.
ESTADOS_ACTIVOS_TECNICO = (Estado.ASIGNADO, Estado.EN_PROCESO, Estado.EN_PAUSA)


def crear_ticket(*, uuid_cliente, nodo, descripcion, criticidad, reportado_por):
    """Crea el ticket y su evento "crear". Si el UUID ya existe (reenvío), devuelve el existente.

    Devuelve (ticket, creado).
    """
    existente = Ticket.objects.filter(uuid_cliente=uuid_cliente).first()
    if existente:
        return existente, False
    try:
        with transaction.atomic():
            ticket = Ticket.objects.create(
                uuid_cliente=uuid_cliente, nodo=nodo, descripcion=descripcion,
                criticidad=criticidad, reportado_por=reportado_por,
            )
            EventoTicket.objects.create(
                ticket=ticket, tipo=TipoEvento.CREAR, estado_desde="", estado_hacia=Estado.REPORTADO,
                actor=reportado_por, fecha=ticket.reportado_en,
            )
    except IntegrityError:
        # Dos envíos simultáneos del mismo reporte: el otro ya lo creó.
        return Ticket.objects.get(uuid_cliente=uuid_cliente), False
    # Fase 6: notificar() al coordinador de la máquina.
    return ticket, True


def ajustar_sla(criticidad, minutos_para_asignar, minutos_para_resolver, usuario):
    """Cambia la regla SLA activa de una criticidad. El cambio queda en el historial con el usuario."""
    if usuario.rol not in (Rol.COORDINADOR, Rol.ADMIN):
        raise TransicionInvalida("Su rol no permite ajustar el SLA.")
    if minutos_para_asignar <= 0 or minutos_para_resolver <= 0:
        raise TransicionInvalida("Los tiempos deben ser mayores que cero.")
    if minutos_para_asignar >= minutos_para_resolver:
        raise TransicionInvalida("El tiempo para asignar debe ser menor que el tiempo para resolver.")
    regla = ReglaSLA.objects.get(criticidad=criticidad, activa=True)
    if (regla.minutos_para_asignar, regla.minutos_para_resolver) == (minutos_para_asignar, minutos_para_resolver):
        return regla, False
    regla.minutos_para_asignar = minutos_para_asignar
    regla.minutos_para_resolver = minutos_para_resolver
    regla.modificada_por = usuario
    regla._change_reason = "Ajuste desde la pantalla del coordinador"
    regla.save()
    return regla, True


def es_coordinador_de(usuario, ticket):
    return usuario.rol == Rol.COORDINADOR and CoordinadorMaquina.objects.filter(
        coordinador=usuario, maquina=ticket.nodo.maquina).exists()


def acciones_permitidas(ticket, usuario):
    """Tipos de evento que `usuario` puede hacer ahora sobre `ticket` (para mostrar los botones)."""
    return [tipo for tipo in TRANSICIONES if _motivo_de_rechazo(ticket, tipo, usuario) is None]


def _motivo_de_rechazo(ticket, tipo, actor):
    regla = TRANSICIONES.get(tipo)
    if regla is None:
        return "Acción desconocida."
    if ticket.estado not in regla.desde:
        return (f"El ticket está «{ticket.get_estado_display()}» y no permite esta acción. "
                "Puede que otra persona lo haya cambiado hace un momento.")
    if actor.rol not in regla.roles:
        return "Su rol no permite esta acción."
    if actor.rol == Rol.TECNICO and ticket.tecnico_id != actor.pk:
        return "Este ticket está asignado a otro técnico."
    if actor.rol == Rol.COORDINADOR and not es_coordinador_de(actor, ticket):
        return "Este ticket no es de una de sus máquinas."
    return None


def _exigir_texto(texto, minimo, nombre):
    if len((texto or "").strip()) < minimo:
        raise TransicionInvalida(f"Escriba {nombre} con al menos {minimo} caracteres.")


def transicionar(ticket, tipo, actor, *, comentario="", tecnico=None, cierre=None):
    """Hace un cambio de estado: valida, actualiza el ticket y crea el EventoTicket.

    - asignar / reasignar: `tecnico` (usuario con rol técnico).
    - pausar: `comentario` = motivo del contra-reporte.
    - reanudar: `comentario` = respuesta (obligatoria si la hace el coordinador).
    - resolver: `cierre` = dict con causa_raiz, accion_correctiva, recomendacion_preventiva y repuestos.
    - rechazar / anular: `comentario` = motivo.

    Los textos se guardan tal como los escribió el usuario. Lanza TransicionInvalida si no se puede.
    """
    with transaction.atomic():
        # Se vuelve a leer dentro de la transacción: otro usuario pudo cambiarlo hace un instante.
        ticket = Ticket.objects.select_related("nodo").get(pk=ticket.pk)
        motivo = _motivo_de_rechazo(ticket, tipo, actor)
        if motivo:
            raise TransicionInvalida(motivo)

        ahora = timezone.now()
        regla = TRANSICIONES[tipo]
        estado_desde = ticket.estado

        if tipo in (TipoEvento.ASIGNAR, TipoEvento.REASIGNAR):
            if tecnico is None or tecnico.rol != Rol.TECNICO or not tecnico.is_active:
                raise TransicionInvalida("Elija un técnico.")
            if tipo == TipoEvento.REASIGNAR and tecnico.pk == ticket.tecnico_id:
                raise TransicionInvalida("Ese técnico ya tiene el ticket.")
            if tipo == TipoEvento.REASIGNAR:
                anterior = ticket.tecnico
                comentario = comentario or f"De {anterior} a {tecnico}."
            ticket.tecnico = tecnico
            ticket.asignado_en = ticket.asignado_en or ahora

        elif tipo == TipoEvento.INICIAR:
            ticket.iniciado_en = ticket.iniciado_en or ahora

        elif tipo == TipoEvento.PAUSAR:
            _exigir_texto(comentario, MIN_CARACTERES_MOTIVO, "el motivo de la pausa")
            ContraReporte.objects.create(ticket=ticket, tecnico=actor, motivo=comentario, fecha=ahora)

        elif tipo == TipoEvento.REANUDAR:
            if actor.rol == Rol.COORDINADOR:
                _exigir_texto(comentario, MIN_CARACTERES_MOTIVO, "la respuesta al contra-reporte")
            pendiente = ticket.contra_reportes.filter(respondido_en__isnull=True).order_by("-fecha").first()
            if pendiente:
                pendiente.respuesta = comentario
                pendiente.respondido_por = actor
                pendiente.respondido_en = ahora
                pendiente.save()

        elif tipo == TipoEvento.RESOLVER:
            cierre = cierre or {}
            _exigir_texto(cierre.get("causa_raiz"), MIN_CARACTERES_CIERRE, "la causa raíz")
            _exigir_texto(cierre.get("accion_correctiva"), MIN_CARACTERES_CIERRE, "la acción correctiva")
            _exigir_texto(cierre.get("recomendacion_preventiva"), MIN_CARACTERES_CIERRE, "la recomendación preventiva")
            CierreTecnico.objects.create(
                ticket=ticket, tecnico=actor, intento=ticket.cierres.count() + 1, creado_en=ahora,
                causa_raiz=cierre["causa_raiz"], accion_correctiva=cierre["accion_correctiva"],
                repuestos=cierre.get("repuestos", ""), recomendacion_preventiva=cierre["recomendacion_preventiva"],
            )
            ticket.resuelto_en = ahora

        elif tipo == TipoEvento.VALIDAR:
            ticket.cerrado_en = ahora

        elif tipo == TipoEvento.RECHAZAR:
            _exigir_texto(comentario, MIN_CARACTERES_MOTIVO, "el motivo del rechazo")
            ticket.resuelto_en = None  # vuelve a trabajo: deberá escribir un cierre nuevo

        elif tipo == TipoEvento.ANULAR:
            _exigir_texto(comentario, MIN_CARACTERES_MOTIVO, "el motivo de la anulación")
            ticket.anulado_en = ahora

        if regla.hacia:
            ticket.estado = regla.hacia
        ticket._change_reason = TipoEvento(tipo).label
        ticket.save()
        evento = EventoTicket.objects.create(
            ticket=ticket, tipo=tipo, estado_desde=estado_desde, estado_hacia=ticket.estado,
            actor=actor, comentario=comentario, fecha=ahora,
        )
    # Fase 6: notificar() según la matriz del plan.
    return ticket, evento
