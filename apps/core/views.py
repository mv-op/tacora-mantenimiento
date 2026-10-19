from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from .menu import pantalla_principal

MENSAJE_PAGINA_VIEJA = (
    "La página estaba desactualizada (por ejemplo, porque alguien ingresó con otro usuario en este mismo "
    "navegador). No se guardó nada. Recárguela e intente de nuevo."
)


@login_required
def inicio(request):
    """Lleva a cada rol a su pantalla principal."""
    return redirect(pantalla_principal(request.user))


@login_required
def cuenta(request):
    return render(request, "cuenta.html")


def fallo_csrf(request, reason=""):
    """Reemplaza la página técnica de Django cuando el código de seguridad del formulario ya no es válido."""
    if request.headers.get("HX-Request"):
        # HTMX no muestra respuestas de error: se recarga la página completa y ahí se ve el aviso.
        messages.warning(request, MENSAJE_PAGINA_VIEJA)
        respuesta = HttpResponse(status=403)
        respuesta["HX-Refresh"] = "true"
        return respuesta
    return render(request, "fallo_csrf.html", {"mensaje": MENSAJE_PAGINA_VIEJA}, status=403)
