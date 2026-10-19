from django.urls import path

from . import views

urlpatterns = [
    path("notificaciones/", views.bandeja, name="notificaciones"),
    path("notificaciones/estado/", views.estado, name="notificaciones_estado"),
    path("notificaciones/leer-todas/", views.marcar_todas, name="notificaciones_leer_todas"),
    path("notificaciones/<int:pk>/abrir/", views.abrir, name="notificacion_abrir"),
    path("notificaciones/<int:pk>/vista/", views.marcar_vista, name="notificacion_vista"),
]
