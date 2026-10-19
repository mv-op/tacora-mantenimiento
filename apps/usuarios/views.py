from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import acceso


def _siguiente(request, por_defecto="inicio"):
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
        return destino
    return por_defecto


@never_cache
def ingresar(request):
    if request.user.is_authenticated:
        return redirect(_siguiente(request))
    error, usuario_escrito = None, ""
    if request.method == "POST":
        usuario_escrito = request.POST.get("usuario", "")
        try:
            usuario = acceso.ingresar(request, usuario_escrito, request.POST.get("clave", ""))
        except acceso.Bloqueado as bloqueo:
            error = (f"Usuario bloqueado por intentos fallidos. "
                     f"Intente de nuevo a las {timezone.localtime(bloqueo.hasta):%H:%M}.")
        else:
            if usuario:
                login(request, usuario)
                acceso.registrar_actividad(request)
                return redirect(_siguiente(request))
            error = "Usuario o contraseña incorrectos."
    return render(request, "usuarios/ingresar.html",
                  {"error": error, "usuario_escrito": usuario_escrito, "next": _siguiente(request, "")})


@require_POST
def salir(request):
    logout(request)
    return redirect("ingresar")


@never_cache
@login_required
def cambiar_clave(request):
    errores = []
    if request.method == "POST":
        nueva, confirmacion = request.POST.get("nueva", ""), request.POST.get("confirmacion", "")
        if not request.user.debe_cambiar_clave and not request.user.check_password(request.POST.get("actual", "")):
            errores.append("La contraseña actual no es correcta.")
        elif nueva != confirmacion:
            errores.append("Las dos contraseñas no coinciden.")
        else:
            try:
                validate_password(nueva, request.user)
            except ValidationError as error:
                errores.extend(error.messages)
        if not errores:
            request.user.set_password(nueva)
            request.user.debe_cambiar_clave = False
            request.user.save(update_fields=["password", "debe_cambiar_clave"])
            update_session_auth_hash(request, request.user)
            messages.success(request, "Contraseña actualizada.")
            return redirect("inicio")
    return render(request, "usuarios/cambiar_clave.html",
                  {"errores": errores, "primera_vez": request.user.debe_cambiar_clave})


@never_cache
@login_required
def terminos(request):
    if request.method == "POST":
        acceso.registrar_aceptacion(request)
        return redirect(_siguiente(request))
    return render(request, "usuarios/terminos.html",
                  {"ya_acepto": acceso.acepto_terminos(request), "next": _siguiente(request, "")})


@require_POST
@login_required
def sesion_seguir(request):
    """Botón "Seguir conectado" y avisos de uso: el middleware ya registró la actividad."""
    return HttpResponse(status=204)
