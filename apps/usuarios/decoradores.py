from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def rol_requerido(*roles):
    """La vista solo la usan usuarios con alguno de estos roles."""
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(request, *args, **kwargs):
            if request.user.rol not in roles:
                raise PermissionDenied("Esta pantalla no es para su rol.")
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador
