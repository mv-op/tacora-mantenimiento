"""Consultas de tickets para las pantallas de coordinador y técnico."""

from django.contrib import messages
from django.db.models import Count, Q

from apps.activos.models import CoordinadorMaquina, Nivel
from apps.usuarios.models import Rol, Usuario

from . import sla
from .models import Criticidad, Ticket, TipoEvento
from .servicios import ESTADOS_ACTIVOS_TECNICO, TransicionInvalida, transicionar

ORDEN_CRITICIDAD = {Criticidad.CRITICA: 0, Criticidad.URGENTE: 1, Criticidad.IMPORTANTE: 2}


def maquinas_de(coordinador):
    return [cm.maquina for cm in CoordinadorMaquina.objects.filter(coordinador=coordinador).select_related("maquina")]


def tickets_de_maquinas(maquinas):
    """Tickets cuyo activo cuelga de alguna de estas máquinas (a cualquier profundidad del árbol)."""
    filtro = Q()
    camino = "nodo"
    for _ in Nivel:
        filtro |= Q(**{f"{camino}__in": maquinas})
        camino += "__padre"
    return Ticket.objects.filter(filtro)


def con_semaforo(tickets):
    """Agrega `.sla` a cada ticket y los ordena: más crítico primero y, dentro, el más cerca de vencer."""
    reglas = sla.reglas_activas()
    lista = list(tickets)
    for ticket in lista:
        ticket.sla = sla.semaforo(ticket, reglas)
    lista.sort(key=lambda t: (ORDEN_CRITICIDAD.get(t.criticidad, 9), -(t.sla.fraccion if t.sla else 0)))
    return lista


def tecnicos_con_carga():
    """Técnicos activos con su número de tareas activas, el menos cargado primero."""
    return (Usuario.objects.filter(rol=Rol.TECNICO, is_active=True)
            .annotate(carga=Count("tickets_asignados", filter=Q(tickets_asignados__estado__in=ESTADOS_ACTIVOS_TECNICO)))
            .order_by("carga", "nombre_visible", "username"))


def ultimo_rechazo(ticket):
    """Motivo del último rechazo, si el ticket volvió a trabajo por un rechazo y aún no se ha resuelto de nuevo."""
    ultimo = ticket.eventos.filter(tipo__in=[TipoEvento.RECHAZAR, TipoEvento.RESOLVER]).order_by("-fecha", "-pk").first()
    return ultimo if ultimo and ultimo.tipo == TipoEvento.RECHAZAR else None


def ejecutar(request, ticket, tipo, **datos):
    """Llama a transicionar() desde una vista y deja el mensaje para el usuario. Devuelve True si se hizo."""
    try:
        transicionar(ticket, tipo, request.user, **datos)
    except TransicionInvalida as error:
        messages.error(request, str(error))
        return False
    messages.success(request, f"Listo: {TipoEvento(tipo).label.lower()}.")
    return True
