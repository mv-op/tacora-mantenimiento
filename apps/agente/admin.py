from django.contrib import admin

from .models import HallazgoAgente


@admin.register(HallazgoAgente)
class HallazgoAgenteAdmin(admin.ModelAdmin):
    list_display = ["creado_en", "tipo_regla", "severidad", "nodo", "ticket", "estado"]
    list_filter = ["tipo_regla", "severidad", "estado"]
    readonly_fields = ["tipo_regla", "nodo", "ticket", "severidad", "detalle", "creado_en"]

    def has_add_permission(self, request):
        return False
