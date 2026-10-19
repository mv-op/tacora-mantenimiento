from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

from . import acceso

# Rutas que no exigen los pasos previos (cambio de contraseña, términos).
LIBRES = ("ingresar", "salir", "cambiar_clave", "terminos", "sesion_seguir")


def _redirigir(request, url):
    """Redirige también las peticiones HTMX (que si no cambiarían solo un pedazo de la página)."""
    if request.headers.get("HX-Request"):
        respuesta = HttpResponse(status=204)
        respuesta["HX-Redirect"] = url
        return respuesta
    return redirect(url)


class AccesoMiddleware:
    """En cada petición: cierra la sesión por inactividad y exige cambio de contraseña y términos."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/" + settings.STATIC_URL.lstrip("/")):
            return self.get_response(request)

        if request.user.is_authenticated:
            if acceso.sesion_vencida(request):
                logout(request)
                messages.info(request, "Su sesión se cerró por inactividad.")
                return _redirigir(request, reverse("ingresar"))

            # Las consultas automáticas (p. ej. la campana) no cuentan como uso.
            if not request.headers.get("X-Consulta-Automatica"):
                acceso.registrar_actividad(request)

            try:
                nombre = resolve(request.path_info).url_name
            except Resolver404:
                nombre = None
            if nombre not in LIBRES:
                if request.user.debe_cambiar_clave:
                    return _redirigir(request, reverse("cambiar_clave"))
                if not acceso.acepto_terminos(request):
                    return _redirigir(request, reverse("terminos") + "?" + urlencode({"next": request.get_full_path()}))

        return self.get_response(request)
