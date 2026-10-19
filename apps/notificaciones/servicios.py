"""Notificaciones dentro de la app. Todas se crean con `notificar()`; nada más escribe en Notificacion.

Las demás funciones deciden a quién avisar (la matriz del plan) y llaman a `notificar()`.
"""

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.activos.models import CoordinadorMaquina
from apps.tickets.models import Criticidad, TipoEvento
from apps.usuarios.models import Rol, Usuario

from .models import Notificacion, Prioridad, TipoNotificacion

T = TipoNotificacion


def notificar(destinatarios, tipo, mensaje, *, excluir=None, prioridad=Prioridad.NORMAL,
              ticket=None, evento=None, nodo=None, hallazgo=None, etapa="", umbral=0):
    """Crea un aviso por destinatario activo, sin repetir. Nunca avisa a `excluir` (quien hizo la acción).

    Devuelve la lista de notificaciones creadas.
    """
    creadas, vistos = [], set()
    for usuario in destinatarios:
        if usuario is None or not usuario.is_active or usuario.pk in vistos or (excluir and usuario.pk == excluir.pk):
            continue
        vistos.add(usuario.pk)
        try:
            with transaction.atomic():
                creadas.append(Notificacion.objects.create(
                    destinatario=usuario, tipo=tipo, mensaje=mensaje, prioridad=prioridad, ticket=ticket,
                    evento=evento, nodo=nodo, hallazgo=hallazgo, etapa=etapa, umbral=umbral,
                ))
        except IntegrityError:
            pass  # ya tenía este aviso (restricciones únicas del modelo)
    return creadas


def coordinadores_de(ticket):
    return list(Usuario.objects.filter(rol=Rol.COORDINADOR, maquinas_coordinadas__maquina=ticket.nodo.maquina))


def _resumen(ticket):
    return f"#{ticket.pk} · {ticket.nodo.ruta}"


def notificar_evento(evento, tecnico_anterior=None):
    """Avisos por cada cambio de estado de un ticket, según la matriz del plan."""
    ticket, actor = evento.ticket, evento.actor
    operador, tecnico = ticket.reportado_por, ticket.tecnico
    comun = {"ticket": ticket, "evento": evento, "excluir": actor}
    critico = ticket.criticidad == Criticidad.CRITICA

    if evento.tipo == TipoEvento.CREAR:
        tipo = T.REPORTE_CRITICO if critico else T.NUEVO_REPORTE
        notificar(coordinadores_de(ticket), tipo,
                  f"{ticket.get_criticidad_display()}: {_resumen(ticket)}. {ticket.descripcion[:120]}",
                  prioridad=Prioridad.ALTA if critico else Prioridad.NORMAL, **comun)

    elif evento.tipo in (TipoEvento.ASIGNAR, TipoEvento.REASIGNAR):
        notificar([tecnico], T.TICKET_ASIGNADO, f"Le asignaron la orden {_resumen(ticket)}.",
                  prioridad=Prioridad.ALTA if critico else Prioridad.NORMAL, **comun)
        if evento.tipo == TipoEvento.ASIGNAR:
            notificar([operador], T.TICKET_ASIGNADO, f"Su reporte {_resumen(ticket)} fue asignado a {tecnico}.", **comun)
        else:
            notificar([tecnico_anterior], T.TICKET_REASIGNADO,
                      f"La orden {_resumen(ticket)} pasó a {tecnico}. Ya no está a su cargo.", **comun)

    elif evento.tipo == TipoEvento.INICIAR:
        notificar([operador], T.TRABAJO_INICIADO, f"{tecnico} empezó a trabajar en su reporte {_resumen(ticket)}.", **comun)

    elif evento.tipo == TipoEvento.PAUSAR:
        notificar(coordinadores_de(ticket), T.CONTRA_REPORTE,
                  f"{tecnico} pausó {_resumen(ticket)}: {evento.comentario}", **comun)

    elif evento.tipo == TipoEvento.REANUDAR and actor.rol == Rol.COORDINADOR:
        notificar([tecnico], T.RESPUESTA_CONTRA_REPORTE,
                  f"{actor} respondió su contra-reporte de {_resumen(ticket)}: {evento.comentario}", **comun)

    elif evento.tipo == TipoEvento.RESOLVER:
        notificar(coordinadores_de(ticket), T.RESUELTO_PENDIENTE,
                  f"{tecnico} terminó {_resumen(ticket)}. Revise el cierre y valídelo.", **comun)
        notificar([operador], T.RESUELTO_PENDIENTE,
                  f"Su reporte {_resumen(ticket)} fue resuelto y espera validación.", **comun)

    elif evento.tipo == TipoEvento.RECHAZAR:
        notificar([tecnico], T.CIERRE_RECHAZADO, f"{actor} rechazó su cierre de {_resumen(ticket)}: {evento.comentario}",
                  **comun)

    elif evento.tipo == TipoEvento.VALIDAR:
        notificar([operador], T.TICKET_CERRADO, f"Su reporte {_resumen(ticket)} quedó cerrado.", **comun)
        notificar([tecnico], T.TICKET_CERRADO, f"{actor} validó y cerró la orden {_resumen(ticket)}.", **comun)

    elif evento.tipo == TipoEvento.ANULAR:
        notificar([operador], T.TICKET_ANULADO, f"Su reporte {_resumen(ticket)} fue anulado: {evento.comentario}",
                  **comun)


def notificar_sla(ticket, semaforo):
    """Aviso de SLA al 70 % (por vencer) y al 100 % (vencido, con sonido). Uno por plazo y umbral."""
    if semaforo is None or semaforo.congelado or semaforo.fraccion < 0.7:
        return []
    vencido = semaforo.fraccion >= 1
    plazo = "asignar" if semaforo.meta == "asignar" else "resolver"
    if vencido:
        mensaje = f"Se venció el plazo para {plazo}: {_resumen(ticket)}."
    else:
        mensaje = f"El plazo para {plazo} vence a las {timezone.localtime(semaforo.limite):%H:%M}: {_resumen(ticket)}."
    return notificar(
        coordinadores_de(ticket) + [ticket.tecnico], T.SLA_VENCIDO if vencido else T.SLA_POR_VENCER,
        mensaje, ticket=ticket, etapa=semaforo.meta, umbral=100 if vencido else 70,
        prioridad=Prioridad.ALTA if vencido else Prioridad.NORMAL,
    )


def notificar_nodo_pendiente(nodo):
    administradores = Usuario.objects.filter(rol=Rol.ADMIN, is_active=True)
    return notificar(administradores, T.NODO_PENDIENTE,
                     f"{nodo.creado_por} creó «{nodo.ruta}» ({nodo.get_nivel_display()}). Revíselo en el admin.",
                     nodo=nodo, excluir=nodo.creado_por)


def url_destino(notificacion):
    """A dónde lleva el aviso, según quién lo recibe."""
    usuario, ticket = notificacion.destinatario, notificacion.ticket
    if ticket:
        if usuario.rol == Rol.COORDINADOR and CoordinadorMaquina.objects.filter(
                coordinador=usuario, maquina=ticket.nodo.maquina).exists():
            return reverse("bandeja_ticket", args=[ticket.pk])
        if usuario.rol == Rol.TECNICO and ticket.tecnico_id == usuario.pk:
            return reverse("orden", args=[ticket.pk])
        if ticket.reportado_por_id == usuario.pk:
            return reverse("mi_reporte", args=[ticket.pk])
        if usuario.is_staff:
            return reverse("admin:tickets_ticket_change", args=[ticket.pk])
    if notificacion.nodo_id and usuario.is_staff:
        return reverse("admin:activos_nodoactivo_change", args=[notificacion.nodo_id])
    return reverse("notificaciones")
