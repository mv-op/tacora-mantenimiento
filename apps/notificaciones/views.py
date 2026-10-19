"""Campana, bandeja de notificaciones y la consulta liviana que hace el navegador cada 20 segundos."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notificacion, Prioridad
from .servicios import url_destino

MAX_NUEVAS = 10


def _mias(request):
    return Notificacion.objects.filter(destinatario=request.user)


def _datos(notificacion):
    return {
        "id": notificacion.pk,
        "tipo": notificacion.get_tipo_display(),
        "mensaje": notificacion.mensaje,
        "url": f"/notificaciones/{notificacion.pk}/abrir/",
        "alta": notificacion.prioridad == Prioridad.ALTA,
        "tarjeta": notificacion.estilo["tarjeta"],
        "etiqueta": notificacion.estilo["etiqueta"],
        "hora": f"{timezone.localtime(notificacion.creada_en):%H:%M}",
    }


@login_required
def estado(request):
    """Contador, avisos nuevos (id mayor que `despues`) y avisos fijos sin ver. La pide notificaciones.js."""
    sin_leer = _mias(request).filter(leida_en__isnull=True)
    despues = request.GET.get("despues", "")
    nuevas = sin_leer.filter(pk__gt=int(despues)).order_by("pk")[:MAX_NUEVAS] if despues.isdigit() else []
    fijas = sin_leer.filter(prioridad=Prioridad.ALTA).select_related("ticket").order_by("pk")
    ultima = _mias(request).order_by("-pk").values_list("pk", flat=True).first() or 0
    return JsonResponse({
        "sin_leer": sin_leer.count(),
        "ultima": ultima,
        "nuevas": [_datos(n) for n in nuevas],
        "fijas": [_datos(n) for n in fijas],
    })


@login_required
def bandeja(request):
    notificaciones = _mias(request).select_related("ticket", "ticket__nodo")[:100]
    return render(request, "notificaciones/bandeja.html", {"notificaciones": notificaciones})


@login_required
def abrir(request, pk):
    """Marca el aviso como leído y lleva a su ticket (o a lo que corresponda)."""
    notificacion = get_object_or_404(_mias(request).select_related("ticket", "ticket__nodo"), pk=pk)
    if notificacion.leida_en is None:
        notificacion.leida_en = timezone.now()
        notificacion.save(update_fields=["leida_en"])
    return redirect(url_destino(notificacion))


@require_POST
@login_required
def marcar_vista(request, pk):
    _mias(request).filter(pk=pk, leida_en__isnull=True).update(leida_en=timezone.now())
    return HttpResponse(status=204)


@require_POST
@login_required
def marcar_todas(request):
    _mias(request).filter(leida_en__isnull=True).update(leida_en=timezone.now())
    return redirect("notificaciones")
