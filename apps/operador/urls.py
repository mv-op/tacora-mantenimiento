from django.urls import path

from . import views

urlpatterns = [
    path("reportar/", views.mosaico, name="reportar"),
    path("reportar/<int:nodo_id>/", views.mosaico, name="reportar_nodo"),
    path("reportar/crear/", views.crear_nodo, name="crear_nodo"),
    path("reportar/sugerencias/", views.sugerencias, name="sugerencias"),
    path("reportar/<int:nodo_id>/describir/", views.describir, name="describir"),
    path("reportes/enviar/", views.enviar_reporte, name="enviar_reporte"),
    path("reportes/", views.mis_reportes, name="mis_reportes"),
    path("reportes/<int:pk>/", views.mi_reporte, name="mi_reporte"),
]
