from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # El admin usa el mismo ingreso de la app (con bloqueo por intentos).
    path("admin/login/", RedirectView.as_view(pattern_name="ingresar", query_string=True)),
    path("admin/", admin.site.urls),
    path("", include("apps.usuarios.urls")),
    path("", include("apps.operador.urls")),
    path("", include("apps.core.urls")),
]
