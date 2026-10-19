"""Reglas de acceso: ingreso con bloqueo por intentos, inactividad y términos."""

import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.utils import timezone

from .models import AceptacionTerminos, Usuario

CLAVE_ACTIVIDAD = "ultima_actividad"
CLAVE_TERMINOS = "terminos_aceptados"


class Bloqueado(Exception):
    def __init__(self, hasta):
        self.hasta = hasta


def ingresar(request, username, password):
    """Devuelve el usuario si la contraseña es correcta; None si no. Lanza Bloqueado si está bloqueado."""
    usuario = Usuario.objects.filter(username__iexact=username.strip()).first()
    if usuario and usuario.esta_bloqueado:
        raise Bloqueado(usuario.bloqueado_hasta)

    autenticado = authenticate(request, username=usuario.username if usuario else username, password=password)
    if autenticado:
        if autenticado.intentos_fallidos or autenticado.bloqueado_hasta:
            autenticado.intentos_fallidos = 0
            autenticado.bloqueado_hasta = None
            autenticado.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
        return autenticado

    if usuario:
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= settings.INTENTOS_MAXIMOS:
            usuario.intentos_fallidos = 0
            usuario.bloqueado_hasta = timezone.now() + timedelta(minutes=settings.MINUTOS_BLOQUEO)
            usuario.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
            raise Bloqueado(usuario.bloqueado_hasta)
        usuario.save(update_fields=["intentos_fallidos"])
    return None


def registrar_actividad(request):
    request.session[CLAVE_ACTIVIDAD] = int(time.time())


def sesion_vencida(request):
    ultima = request.session.get(CLAVE_ACTIVIDAD)
    return ultima is not None and time.time() - ultima > settings.SESION_INACTIVIDAD_MINUTOS * 60


def acepto_terminos(request):
    """Revisa la versión vigente; el resultado se guarda en la sesión para no consultar en cada página."""
    if request.session.get(CLAVE_TERMINOS) == settings.TERMINOS_VERSION:
        return True
    if AceptacionTerminos.objects.filter(usuario=request.user, version=settings.TERMINOS_VERSION).exists():
        request.session[CLAVE_TERMINOS] = settings.TERMINOS_VERSION
        return True
    return False


def registrar_aceptacion(request):
    # Detrás de Nginx, REMOTE_ADDR es el propio servidor; la IP real viene en X-Forwarded-For.
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = reenviada.split(",")[0].strip() or request.META.get("REMOTE_ADDR")
    AceptacionTerminos.objects.create(
        usuario=request.user, version=settings.TERMINOS_VERSION, ip=ip or None,
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
    request.session[CLAVE_TERMINOS] = settings.TERMINOS_VERSION
