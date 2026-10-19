from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AceptacionTerminos, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ["username", "nombre_visible", "rol", "is_active", "tiene_pin", "bloqueado_hasta"]
    list_filter = ["rol", "is_active", "debe_cambiar_clave"]
    search_fields = ["username", "nombre_visible", "first_name", "last_name"]
    readonly_fields = ["tiene_pin", "intentos_fallidos", "last_login", "date_joined"]
    fieldsets = UserAdmin.fieldsets + (
        ("Mantenimiento", {"fields": ["rol", "nombre_visible", "debe_cambiar_clave", "tiene_pin",
                                      "intentos_fallidos", "bloqueado_hasta"]}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Mantenimiento", {"fields": ["rol", "nombre_visible"]}),
    )

    @admin.display(boolean=True, description="tiene PIN")
    def tiene_pin(self, obj):
        return obj.tiene_pin


@admin.register(AceptacionTerminos)
class AceptacionTerminosAdmin(admin.ModelAdmin):
    list_display = ["usuario", "version", "fecha", "ip"]
    list_filter = ["version"]
    readonly_fields = ["usuario", "version", "fecha", "ip", "user_agent"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
