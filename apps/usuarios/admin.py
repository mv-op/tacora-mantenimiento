from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.db.models import Count

from apps.activos.models import CoordinadorMaquina, Nivel, NodoActivo

from .models import AceptacionTerminos, Rol, Usuario


def campo_maquinas():
    """Selector de dos listas (disponibles / elegidas) con buscador y "Elegir todas"."""
    return forms.ModelMultipleChoiceField(
        queryset=NodoActivo.objects.filter(nivel=Nivel.MAQUINA, is_active=True).order_by("nombre"),
        required=False, label="Máquinas que coordina",
        widget=FilteredSelectMultiple("máquinas", is_stacked=False),
        help_text="Solo para el rol coordinador. Verá en su bandeja los reportes de todas estas máquinas. "
                  "Una máquina puede tener varios coordinadores (por ejemplo, producción y mantenimiento).",
    )


class MaquinasMixin:
    def iniciar_maquinas(self):
        if self.instance.pk:
            self.fields["maquinas"].initial = list(
                CoordinadorMaquina.objects.filter(coordinador=self.instance).values_list("maquina", flat=True))

    def clean(self):
        datos = super().clean()
        if datos.get("maquinas") and datos.get("rol") != Rol.COORDINADOR:
            self.add_error("maquinas", "Solo los usuarios con rol coordinador tienen máquinas. Quítelas o cambie el rol.")
        return datos


class CrearUsuarioForm(MaquinasMixin, forms.ModelForm):
    """Sin campos de contraseña: se asigna la contraseña inicial común."""

    maquinas = campo_maquinas()

    class Meta:
        model = Usuario
        fields = ["username", "nombre_visible", "first_name", "last_name", "rol"]


class EditarUsuarioForm(MaquinasMixin, UserChangeForm):
    maquinas = campo_maquinas()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.iniciar_maquinas()


def _poner_clave_inicial(usuario):
    usuario.set_password(settings.CLAVE_INICIAL)
    usuario.debe_cambiar_clave = True
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    add_form = CrearUsuarioForm
    form = EditarUsuarioForm
    list_display = ["username", "nombre_visible", "rol", "num_maquinas", "is_active", "debe_cambiar_clave",
                    "bloqueado_hasta", "last_login"]
    list_filter = ["rol", "is_active", "debe_cambiar_clave"]
    search_fields = ["username", "nombre_visible", "first_name", "last_name"]
    readonly_fields = ["intentos_fallidos", "last_login", "date_joined"]
    fieldsets = [
        (None, {"fields": ["username", "password"]}),
        ("Datos", {"fields": ["nombre_visible", "first_name", "last_name", "email"]}),
        ("Mantenimiento", {"fields": ["rol", "is_active", "debe_cambiar_clave", "intentos_fallidos", "bloqueado_hasta"]}),
        ("Máquinas (coordinadores)", {"fields": ["maquinas"]}),
        ("Fechas", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {
            "fields": ["username", "nombre_visible", "first_name", "last_name", "rol"],
            "description": "La contraseña inicial se asigna sola. El usuario la cambia en su primer ingreso.",
        }),
        ("Máquinas (coordinadores)", {"fields": ["maquinas"]}),
    ]
    actions = ["restablecer_clave", "desbloquear"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_num_maquinas=Count("maquinas_coordinadas"))

    @admin.display(description="máquinas", ordering="_num_maquinas")
    def num_maquinas(self, obj):
        return obj._num_maquinas if obj.rol == Rol.COORDINADOR else "—"

    def save_model(self, request, obj, form, change):
        if not change:
            _poner_clave_inicial(obj)
        # El rol administrador es quien entra al admin de Django.
        obj.is_staff = obj.is_superuser = obj.rol == Rol.ADMIN
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Deja en CoordinadorMaquina exactamente las máquinas elegidas.
        usuario = form.instance
        elegidas = {m.pk for m in form.cleaned_data.get("maquinas") or []}
        actuales = set(CoordinadorMaquina.objects.filter(coordinador=usuario).values_list("maquina", flat=True))
        CoordinadorMaquina.objects.filter(coordinador=usuario, maquina__in=actuales - elegidas).delete()
        CoordinadorMaquina.objects.bulk_create(
            [CoordinadorMaquina(coordinador=usuario, maquina_id=pk) for pk in elegidas - actuales])

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
