"""Pantallas del técnico: sus órdenes, iniciar, pausar con contra-reporte, reanudar y finalizar con cierre."""

from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.tickets import sla
from apps.tickets.consultas import con_semaforo, ejecutar, ultimo_rechazo
from apps.tickets.models import Estado, Ticket, TipoEvento
from apps.tickets.servicios import (ESTADOS_ACTIVOS_TECNICO, MIN_CARACTERES_CIERRE, MIN_CARACTERES_MOTIVO,
                                    acciones_permitidas)
from apps.usuarios.decoradores import rol_requerido
from apps.usuarios.models import Rol

CAMPOS_CIERRE = ["causa_raiz", "accion_correctiva", "repuestos", "recomendacion_preventiva"]


def _mi_orden(request, pk):
    return get_object_or_404(Ticket.objects.select_related("nodo", "reportado_por"), pk=pk, tecnico=request.user)


@rol_requerido(Rol.TECNICO)
def mis_ordenes(request):
    activas = con_semaforo(Ticket.objects.filter(tecnico=request.user, estado__in=ESTADOS_ACTIVOS_TECNICO)
                           .select_related("nodo"))
    por_validar = con_semaforo(Ticket.objects.filter(tecnico=request.user, estado=Estado.RESUELTO).select_related("nodo"))
    return render(request, "tecnico/mis_ordenes.html", {"activas": activas, "por_validar": por_validar})


@rol_requerido(Rol.TECNICO)
def orden(request, pk):
    ticket = _mi_orden(request, pk)
    return render(request, "tecnico/orden.html", {
        "ticket": ticket,
        "s": sla.semaforo(ticket),
        "pausa": sla.tiempo_en_pausa(ticket),
        "acciones": acciones_permitidas(ticket, request.user),
        "rechazo": ultimo_rechazo(ticket) if ticket.estado == Estado.EN_PROCESO else None,
        "contra_reporte": ticket.contra_reportes.first(),
        "eventos": ticket.eventos.select_related("actor"),
        "cierres": ticket.cierres.select_related("tecnico"),
    })


@require_POST
@rol_requerido(Rol.TECNICO)
def iniciar(request, pk):
    ejecutar(request, _mi_orden(request, pk), TipoEvento.INICIAR)
    return redirect("orden", pk)


@require_POST
@rol_requerido(Rol.TECNICO)
def reanudar(request, pk):
    ejecutar(request, _mi_orden(request, pk), TipoEvento.REANUDAR, comentario=request.POST.get("comentario", ""))
    return redirect("orden", pk)


@rol_requerido(Rol.TECNICO)
def pausar(request, pk):
    ticket = _mi_orden(request, pk)
    if request.method == "POST":
        if ejecutar(request, ticket, TipoEvento.PAUSAR, comentario=request.POST.get("motivo", "")):
            return redirect("orden", pk)
    return render(request, "tecnico/pausar.html", {
        "ticket": ticket, "minimo": MIN_CARACTERES_MOTIVO, "motivo": request.POST.get("motivo", ""),
    })


@rol_requerido(Rol.TECNICO)
def finalizar(request, pk):
    ticket = _mi_orden(request, pk)
    cierre = {campo: request.POST.get(campo, "") for campo in CAMPOS_CIERRE}
    if request.method == "POST":
        if ejecutar(request, ticket, TipoEvento.RESOLVER, cierre=cierre):
            return redirect("orden", pk)
    return render(request, "tecnico/finalizar.html", {
        "ticket": ticket, "cierre": cierre, "minimo": MIN_CARACTERES_CIERRE,
        "rechazo": ultimo_rechazo(ticket),
    })
