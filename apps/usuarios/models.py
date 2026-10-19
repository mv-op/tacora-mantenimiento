from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


class Rol(models.TextChoices):
    OPERADOR = "operador", "Operador"
    COORDINADOR = "coordinador", "Coordinador"
    TECNICO = "tecnico", "Técnico"
    ADMIN = "admin", "Administrador"


class UsuarioManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Quien crea un superusuario por consola elige su propia contraseña.
        extra_fields.setdefault("rol", Rol.ADMIN)
        extra_fields.setdefault("debe_cambiar_clave", False)
        return super().create_superuser(username, email, password, **extra_fields)


class Usuario(AbstractUser):
    """Usuario del sistema. Se usa `is_active` de Django para activar o desactivar."""

    rol = models.CharField("rol", max_length=20, choices=Rol.choices, default=Rol.OPERADOR)
    nombre_visible = models.CharField("nombre visible", max_length=120, blank=True)
    debe_cambiar_clave = models.BooleanField("debe cambiar clave", default=True)
    intentos_fallidos = models.PositiveSmallIntegerField("intentos fallidos", default=0)
    bloqueado_hasta = models.DateTimeField("bloqueado hasta", null=True, blank=True)

    objects = UsuarioManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.nombre_visible or self.get_full_name() or self.username

    @property
    def esta_bloqueado(self):
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())


class AceptacionTerminos(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="aceptaciones", verbose_name="usuario"
    )
    version = models.CharField("versión", max_length=20)
    fecha = models.DateTimeField("fecha", auto_now_add=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    user_agent = models.TextField("user agent", blank=True)

    class Meta:
        verbose_name = "aceptación de términos"
        verbose_name_plural = "aceptaciones de términos"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.usuario} · v{self.version}"
