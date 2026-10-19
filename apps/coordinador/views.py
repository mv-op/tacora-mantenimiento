"""Pantallas del coordinador: bandeja de sus máquinas y acciones sobre cada ticket."""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.tickets import servicios, sla
from apps.tickets.consultas import (ORDEN_CRITICIDAD, con_semaforo, ejecutar, maquinas_de, tecnicos_con_carga,
                                    tickets_de_maquinas)
from apps.tickets.models import Criticidad, Estado, ReglaSLA, Ticket, TipoEvento
from apps.tickets.servicios import MIN_CARACTERES_MOTIVO, acciones_permitidas, es_coordinador_de
from apps.usuarios.decoradores import rol_requerido
from apps.usuarios.models import Rol, Usuario

# Acciones de un solo botón (con texto opcional u obligatorio) que llegan por POST.
ACCIONES_CON_TEXTO = {
    "validar": TipoEvento.VALIDAR,
    "rechazar": TipoEvento.RECHAZAR,
    "anular": TipoEvento.ANULAR,
    "responder": TipoEvento.REANUDAR,
}


def _ticket_mio(request, pk):
    ticket = get_object_or_404(Ticket.objects.select_related("nodo", "reportado_por", "tecnico"), pk=pk)
    if not es_coordinador_de(request.user, ticket):
        raise Http404
    return ticket


@rol_requerido(Rol.COORDINADOR)
def bandeja(request):
    maquinas = maquinas_de(request.user)
    abiertos = con_semaforo(tickets_de_maquinas(maquinas).exclude(estado__in=[Estado.CERRADO, Estado.ANULADO])
                            .select_related("nodo", "tecnico"))
    # Columnas del tablero, en el orden en que el coordinador debe atenderlas. Clases completas para Tailwind.
    secciones = [
        {"clave": "por-asignar", "titulo": "Por asignar", "ayuda": "Elija un técnico.",
         "cabecera": "bg-blue-600 text-white", "salto": "bg-blue-100 text-blue-800",
         "tickets": [t for t in abiertos if t.estado == Estado.REPORTADO]},
        {"clave": "contra-reportes", "titulo": "Contra-reportes", "ayuda": "El técnico espera su respuesta.",
         "cabecera": "bg-orange-500 text-white", "salto": "bg-orange-100 text-orange-800",
         "tickets": [t for t in abiertos if t.estado == Estado.EN_PAUSA]},
        {"clave": "por-validar", "titulo": "Por validar", "ayuda": "Revise el cierre: valide o rechace.",
         "cabecera": "bg-teal-600 text-white", "salto": "bg-teal-100 text-teal-800",
         "tickets": [t for t in abiertos if t.estado == Estado.RESUELTO]},
        {"clave": "en-curso", "titulo": "En curso", "ayuda": "Asignados o en trabajo.", "mostrar_estado": True,
         "cabecera": "bg-indigo-600 text-white", "salto": "bg-indigo-100 text-indigo-800",
         "tickets": [t for t in abiertos if t.estado in (Estado.ASIGNADO, Estado.EN_PROCESO)]},
    ]
    return render(request, "coordinador/bandeja.html", {
        "maquinas": maquinas, "secciones": secciones, "tecnicos": tecnicos_con_carga(),
    })


@rol_requerido(Rol.COORDINADOR)
def ticket(request, pk):
    ticket = _ticket_mio(request, pk)
    acciones = acciones_permitidas(ticket, request.user)
    return render(request, "coordinador/ticket.html", {
        "ticket": ticket,
        "s": sla.semaforo(ticket),
        "pausa": sla.tiempo_en_pausa(ticket),
        "acciones": acciones,
        "tecnicos": tecnicos_con_carga() if {TipoEvento.ASIGNAR, TipoEvento.REASIGNAR} & set(acciones) else [],
        "contra_reporte": ticket.contra_reportes.filter(respondido_en__isnull=True).first(),
        "eventos": ticket.eventos.select_related("actor"),
        "cierres": ticket.cierres.select_related("tecnico"),
        "minimo": MIN_CARACTERES_MOTIVO,
    })


@require_POST
@rol_requerido(Rol.COORDINADOR)
def asignar(request, pk):
    ticket = _ticket_mio(request, pk)
    tecnico_id = request.POST.get("tecnico", "")
    tecnico = Usuario.objects.filter(pk=tecnico_id).first() if tecnico_id.isdigit() else None
    # La acción viene de la página que vio el coordinador: si otro coordinador ya asignó mientras tanto,
    # "asignar" falla con un aviso en vez de convertirse en una reasignación sin querer.
    tipo = TipoEvento.REASIGNAR if request.POST.get("tipo") == TipoEvento.REASIGNAR else TipoEvento.ASIGNAR
    if ejecutar(request, ticket, tipo, tecnico=tecnico) and tipo == TipoEvento.ASIGNAR:
        return redirect("bandeja")
    return redirect("bandeja_ticket", pk)


def _minutos(request, prefijo):
    """Lee los campos <prefijo>_horas y <prefijo>_min del formulario y devuelve minutos (o None)."""
    horas, minutos = request.POST.get(f"{prefijo}_horas", "0") or "0", request.POST.get(f"{prefijo}_min", "0") or "0"
    if not (horas.isdigit() and minutos.isdigit()):
        return None
    return int(horas) * 60 + int(minutos)


@rol_requerido(Rol.COORDINADOR)
def ajustar_sla(request):
    if request.method == "POST":
        criticidad = request.POST.get("criticidad", "")
        asignar, resolver = _minutos(request, "asignar"), _minutos(request, "resolver")
        if criticidad not in Criticidad.values or asignar is None or resolver is None:
            messages.error(request, "Escriba horas y minutos con números enteros.")
        else:
            try:
                regla, cambio = servicios.ajustar_sla(criticidad, asignar, resolver, request.user)
            except servicios.TransicionInvalida as error:
                messages.error(request, str(error))
            else:
                if cambio:
                    messages.success(request, f"Plazos actualizados: {regla}.")
                else:
                    messages.info(request, "No hubo cambios.")
        return redirect("ajustar_sla")

    reglas = []
    for regla in ReglaSLA.objects.filter(activa=True):
        regla.asignar = divmod(regla.minutos_para_asignar, 60)
        regla.resolver = divmod(regla.minutos_para_resolver, 60)
        reglas.append(regla)
    reglas.sort(key=lambda r: ORDEN_CRITICIDAD.get(r.criticidad, 9))
    cambios = ReglaSLA.history.select_related("history_user").order_by("-history_date")[:15]
    return render(request, "coordinador/sla.html", {"reglas": reglas, "cambios": cambios})


@rol_requerido(Rol.COORDINADOR)
def maquinas(request):
    lista = maquinas_de(request.user)
    for maquina in lista:
        tickets = tickets_de_maquinas([maquina])
        maquina.total = tickets.count()
        maquina.abiertos = tickets.exclude(estado__in=[Estado.CERRADO, Estado.ANULADO]).count()
    return render(request, "coordinador/maquinas.html", {"maquinas": lista})


@rol_requerido(Rol.COORDINADOR)
def historial_maquina(request, pk):
    maquina = next((m for m in maquinas_de(request.user) if m.pk == pk), None)
    if maquina is None:
        raise Http404
    tickets = list(tickets_de_maquinas([maquina]).select_related("nodo", "tecnico")
                   .prefetch_related("cierres").order_by("-reportado_en")[:200])
    for t in tickets:
        cierres = list(t.cierres.all())
        t.ultimo_cierre = cierres[-1] if cierres else None
    return render(request, "coordinador/historial_maquina.html", {"maquina": maquina, "tickets": tickets})


@require_POST
@rol_requerido(Rol.COORDINADOR)
def accion(request, pk, nombre):
    tipo = ACCIONES_CON_TEXTO.get(nombre)
    if tipo is None:
        raise Http404
    ticket = _ticket_mio(request, pk)
    if ejecutar(request, ticket, tipo, comentario=request.POST.get("comentario", "")) and tipo != TipoEvento.REANUDAR:
        return redirect("bandeja")
    return redirect("bandeja_ticket", pk)
