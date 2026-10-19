from django.conf import settings
from django.core.exceptions import ValidationError


class DistintaDeLaInicial:
    """La contraseña propia no puede ser la contraseña inicial común."""

    def validate(self, password, user=None):
        if password == settings.CLAVE_INICIAL:
            raise ValidationError("La contraseña nueva no puede ser la contraseña inicial.", code="clave_inicial")

    def get_help_text(self):
        return "No puede ser la contraseña inicial."
