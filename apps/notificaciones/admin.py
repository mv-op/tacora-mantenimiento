from django.contrib import admin

from .models import Notificacion


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ["creada_en", "destinatario", "tipo", "ticket", "etapa", "prioridad", "leida_en"]
    list_filter = ["tipo", "prioridad"]

    def has_add_permission(self, request):
        return False  # Solo se crean desde notificar().

    def has_change_permission(self, request, obj=None):
        return False
