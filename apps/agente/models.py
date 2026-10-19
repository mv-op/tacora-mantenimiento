from django.conf import settings
from django.db import models

from apps.activos.models import NodoActivo
from apps.tickets.models import Ticket


class TipoRegla(models.TextChoices):
    FALLAS_REPETIDAS = "fallas_repetidas", "Fallas repetidas en el mismo componente"
    SIN_ASIGNAR = "sin_asignar", "Tickets sin asignar"
    SLA_VENCIDO = "sla_vencido", "SLA vencidos"
    RECHAZOS_REPETIDOS = "rechazos_repetidos", "Rechazos repetidos"
    DUPLICADO_PROBABLE = "duplicado_probable", "Nodos duplicados probables"


class Severidad(models.TextChoices):
    BAJA = "baja", "Baja"
    MEDIA = "media", "Media"
    ALTA = "alta", "Alta"


class EstadoHallazgo(models.TextChoices):
    ABIERTO = "abierto", "Abierto"
    ATENDIDO = "atendido", "Atendido"


class HallazgoAgente(models.Model):
    tipo_regla = models.CharField("tipo de regla", max_length=30, choices=TipoRegla.choices)
    nodo = models.ForeignKey(
        NodoActivo, on_delete=models.PROTECT, null=True, blank=True, related_name="hallazgos", verbose_name="activo"
    )
    ticket = models.ForeignKey(
        Ticket, on_delete=models.PROTECT, null=True, blank=True, related_name="hallazgos", verbose_name="ticket"
    )
    severidad = models.CharField("severidad", max_length=10, choices=Severidad.choices)
    detalle = models.TextField("detalle")
    estado = models.CharField("estado", max_length=10, choices=EstadoHallazgo.choices, default=EstadoHallazgo.ABIERTO)
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    atendido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="atendido por",
    )
    atendido_en = models.DateTimeField("atendido en", null=True, blank=True)

    class Meta:
        verbose_name = "hallazgo del agente"
        verbose_name_plural = "hallazgos del agente"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.get_tipo_regla_display()} · {self.get_severidad_display()}"
