from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import AceptacionTerminos, Rol, Usuario


class CrearUsuarioForm(forms.ModelForm):
    """Sin campos de contraseña: se asigna la contraseña inicial común."""

    class Meta:
        model = Usuario
        fields = ["username", "nombre_visible", "first_name", "last_name", "rol"]


def _poner_clave_inicial(usuario):
    usuario.set_password(settings.CLAVE_INICIAL)
    usuario.debe_cambiar_clave = True
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    add_form = CrearUsuarioForm
    list_display = ["username", "nombre_visible", "rol", "is_active", "debe_cambiar_clave", "bloqueado_hasta", "last_login"]
    list_filter = ["rol", "is_active", "debe_cambiar_clave"]
    search_fields = ["username", "nombre_visible", "first_name", "last_name"]
    readonly_fields = ["intentos_fallidos", "last_login", "date_joined"]
    fieldsets = [
        (None, {"fields": ["username", "password"]}),
        ("Datos", {"fields": ["nombre_visible", "first_name", "last_name", "email"]}),
        ("Mantenimiento", {"fields": ["rol", "is_active", "debe_cambiar_clave", "intentos_fallidos", "bloqueado_hasta"]}),
        ("Fechas", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {
            "fields": ["username", "nombre_visible", "first_name", "last_name", "rol"],
            "description": "La contraseña inicial se asigna sola. El usuario la cambia en su primer ingreso.",
        }),
    ]
    actions = ["restablecer_clave", "desbloquear"]

    def save_model(self, request, obj, form, change):
        if not change:
            _poner_clave_inicial(obj)
        # El rol administrador es quien entra al admin de Django.
        obj.is_staff = obj.is_superuser = obj.rol == Rol.ADMIN
        super().save_model(request, obj, form, change)

    @admin.action(description="Restablecer contraseña inicial")
    def restablecer_clave(self, request, queryset):
        for usuario in queryset:
            _poner_clave_inicial(usuario)
            usuario.save()
        self.message_user(request, "Contraseña inicial restablecida. Deberán cambiarla al ingresar.", messages.SUCCESS)

    @admin.action(description="Desbloquear")
    def desbloquear(self, request, queryset):
        queryset.update(intentos_fallidos=0, bloqueado_hasta=None)
        self.message_user(request, "Usuarios desbloqueados.", messages.SUCCESS)


@admin.register(AceptacionTerminos)
class AceptacionTerminosAdmin(admin.ModelAdmin):
    list_display = ["usuario", "version", "fecha", "ip"]
    list_filter = ["version"]
    readonly_fields = ["usuario", "version", "fecha", "ip", "user_agent"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
