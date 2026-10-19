from django.contrib import admin, messages
from simple_history.admin import SimpleHistoryAdmin

from .models import CoordinadorMaquina, EstadoCuraduria, NodoActivo


class HijosInline(admin.TabularInline):
    model = NodoActivo
    fk_name = "padre"
    fields = ["nombre", "nivel", "origen", "estado_curaduria", "is_active"]
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name_plural = "hijos"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(NodoActivo)
class NodoActivoAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "nivel", "ruta", "origen", "estado_curaduria", "is_active"]
    list_filter = ["nivel", "origen", "estado_curaduria", "is_active"]
    search_fields = ["nombre", "nombre_normalizado"]
    autocomplete_fields = ["padre"]
    readonly_fields = ["ruta", "nombre_normalizado", "fusionado_en", "creado_por", "creado_en", "actualizado_en"]
    fields = ["nombre", "nivel", "padre", "ruta", "nombre_normalizado", "origen", "estado_curaduria", "is_active",
              "fusionado_en", "creado_por", "creado_en", "actualizado_en"]
    inlines = [HijosInline]
    actions = ["aprobar", "desactivar"]

    def has_delete_permission(self, request, obj=None):
        return False  # Los nodos nunca se borran.

    def save_model(self, request, obj, form, change):
        if not change and not obj.creado_por_id:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Aprobar curaduría")
    def aprobar(self, request, queryset):
        for nodo in queryset.filter(estado_curaduria=EstadoCuraduria.PENDIENTE):
            nodo.estado_curaduria = EstadoCuraduria.APROBADO
            nodo.save()  # save() uno a uno para que quede en el historial.
        self.message_user(request, "Nodos aprobados.", messages.SUCCESS)

    @admin.action(description="Desactivar (no se borra)")
    def desactivar(self, request, queryset):
        for nodo in queryset.filter(is_active=True):
            nodo.is_active = False
            nodo.save()
        self.message_user(request, "Nodos desactivados.", messages.SUCCESS)


@admin.register(CoordinadorMaquina)
class CoordinadorMaquinaAdmin(admin.ModelAdmin):
    list_display = ["coordinador", "maquina"]
    list_filter = ["coordinador"]
    autocomplete_fields = ["maquina"]
