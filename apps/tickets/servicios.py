"""Funciones de servicio de tickets. Las vistas nunca cambian el estado directamente."""

from django.db import IntegrityError, transaction

from .models import Estado, EventoTicket, Ticket, TipoEvento

MIN_CARACTERES_DESCRIPCION = 20


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
