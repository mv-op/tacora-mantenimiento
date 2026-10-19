from django.urls import path

from . import views

urlpatterns = [
    path("ingresar/", views.ingresar, name="ingresar"),
    path("salir/", views.salir, name="salir"),
    path("cambiar-clave/", views.cambiar_clave, name="cambiar_clave"),
    path("terminos/", views.terminos, name="terminos"),
    path("sesion/seguir/", views.sesion_seguir, name="sesion_seguir"),
]
