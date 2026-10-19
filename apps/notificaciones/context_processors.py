from .models import Notificacion


def campana(request):
    """Contador inicial de la campana y último aviso, para que al cargar no reaparezcan avisos viejos."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    mias = Notificacion.objects.filter(destinatario=request.user)
    return {
        "campana_sin_leer": mias.filter(leida_en__isnull=True).count(),
        "campana_ultima": mias.order_by("-pk").values_list("pk", flat=True).first() or 0,
    }
