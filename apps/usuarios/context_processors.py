from django.conf import settings


def sesion(request):
    return {"inactividad_minutos": settings.SESION_INACTIVIDAD_MINUTOS, "terminos_version": settings.TERMINOS_VERSION}
