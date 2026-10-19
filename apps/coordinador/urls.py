from django.urls import path

from . import views

urlpatterns = [
    path("bandeja/", views.bandeja, name="bandeja"),
    path("bandeja/<int:pk>/", views.ticket, name="bandeja_ticket"),
    path("bandeja/<int:pk>/asignar/", views.asignar, name="bandeja_asignar"),
    path("bandeja/<int:pk>/<slug:nombre>/", views.accion, name="bandeja_accion"),
    path("sla/", views.ajustar_sla, name="ajustar_sla"),
    path("maquinas/", views.maquinas, name="maquinas"),
    path("maquinas/<int:pk>/", views.historial_maquina, name="historial_maquina"),
]
