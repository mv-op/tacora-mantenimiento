from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """Usuario del sistema. Los campos de rol, PIN, etc. se agregan en la Fase 2."""

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
