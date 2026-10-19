from django.urls import path

from . import views

urlpatterns = [
    path("ordenes/", views.mis_ordenes, name="mis_ordenes"),
    path("ordenes/<int:pk>/", views.orden, name="orden"),
    path("ordenes/<int:pk>/iniciar/", views.iniciar, name="orden_iniciar"),
    path("ordenes/<int:pk>/pausar/", views.pausar, name="orden_pausar"),
    path("ordenes/<int:pk>/reanudar/", views.reanudar, name="orden_reanudar"),
    path("ordenes/<int:pk>/finalizar/", views.finalizar, name="orden_finalizar"),
]
