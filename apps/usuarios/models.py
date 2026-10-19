from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.TextChoices):
    OPERADOR = "operador", "Operador"
    COORDINADOR = "coordinador", "Coordinador"
    TECNICO = "tecnico", "Técnico"
    ADMIN = "admin", "Administrador"


class Usuario(AbstractUser):
    """Usuario del sistema. Se usa `is_active` de Django para activar o desactivar."""

    rol = models.CharField("rol", max_length=20, choices=Rol.choices, default=Rol.OPERADOR)
    nombre_visible = models.CharField("nombre visible", max_length=120, blank=True)
    debe_cambiar_clave = models.BooleanField("debe cambiar clave", default=True)
    pin = models.CharField("PIN (hash)", max_length=128, blank=True)
    intentos_fallidos = models.PositiveSmallIntegerField("intentos fallidos", default=0)
    bloqueado_hasta = models.DateTimeField("bloqueado hasta", null=True, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.nombre_visible or self.get_full_name() or self.username

    def set_pin(self, pin_plano):
        self.pin = make_password(pin_plano)

    def check_pin(self, pin_plano):
        return bool(self.pin) and check_password(pin_plano, self.pin)

    @property
    def tiene_pin(self):
        return bool(self.pin)


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
