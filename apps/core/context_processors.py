from .menu import menu_de


def menu(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    actual = request.resolver_match.url_name if request.resolver_match else None
    return {"menu": [(opcion, actual in opcion.pantallas) for opcion in menu_de(request.user)]}
