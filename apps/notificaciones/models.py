from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.activos.models import NodoActivo
from apps.agente.models import HallazgoAgente
from apps.tickets.models import EventoTicket, Ticket


class TipoNotificacion(models.TextChoices):
    NUEVO_REPORTE = "nuevo_reporte", "Nuevo reporte"
    REPORTE_CRITICO = "reporte_critico", "Reporte crítico"
    TICKET_ASIGNADO = "ticket_asignado", "Ticket asignado"
    TRABAJO_INICIADO = "trabajo_iniciado", "Técnico inicia trabajo"
    CONTRA_REPORTE = "contra_reporte", "Contra-reporte"
    RESPUESTA_CONTRA_REPORTE = "respuesta_contra_reporte", "Respuesta a contra-reporte"
    RESUELTO_PENDIENTE = "resuelto_pendiente", "Resuelto, pendiente de validar"
    CIERRE_RECHAZADO = "cierre_rechazado", "Cierre rechazado"
    TICKET_CERRADO = "ticket_cerrado", "Ticket cerrado"
    SLA_POR_VENCER = "sla_por_vencer", "SLA por vencer"
    SLA_VENCIDO = "sla_vencido", "SLA vencido"
    NODO_PENDIENTE = "nodo_pendiente", "Nodo nuevo pendiente de curaduría"
    HALLAZGO_AGENTE = "hallazgo_agente", "Hallazgo del agente"


TIPOS_SLA = [TipoNotificacion.SLA_POR_VENCER, TipoNotificacion.SLA_VENCIDO]


class Prioridad(models.TextChoices):
    NORMAL = "normal", "Normal"
    ALTA = "alta", "Alta (suena y queda fija)"


class Notificacion(models.Model):
    """Solo se crean desde `notificar()` (Fase 6)."""

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="notificaciones", verbose_name="destinatario"
    )
    tipo = models.CharField("tipo", max_length=30, choices=TipoNotificacion.choices)
    ticket = models.ForeignKey(
        Ticket, on_delete=models.PROTECT, null=True, blank=True, related_name="notificaciones", verbose_name="ticket"
    )
    evento = models.ForeignKey(
        EventoTicket, on_delete=models.PROTECT, null=True, blank=True, related_name="notificaciones",
        verbose_name="evento",
    )
    nodo = models.ForeignKey(
        NodoActivo, on_delete=models.PROTECT, null=True, blank=True, related_name="notificaciones", verbose_name="activo"
    )
    hallazgo = models.ForeignKey(
        HallazgoAgente, on_delete=models.PROTECT, null=True, blank=True, related_name="notificaciones",
        verbose_name="hallazgo",
    )
    umbral = models.PositiveSmallIntegerField("umbral (%)", default=0, help_text="70 o 100 para avisos de SLA; 0 si no aplica.")
    mensaje = models.TextField("mensaje")
    prioridad = models.CharField("prioridad", max_length=10, choices=Prioridad.choices, default=Prioridad.NORMAL)
    leida_en = models.DateTimeField("leída en", null=True, blank=True)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    class Meta:
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"
        ordering = ["-creada_en"]
        indexes = [models.Index(fields=["destinatario", "leida_en"])]
        constraints = [
            # Un aviso por destinatario y transición (un rechazo repetido sí vuelve a avisar).
            models.UniqueConstraint(
                fields=["destinatario", "evento", "tipo"], condition=Q(evento__isnull=False),
                name="notificacion_unica_por_evento",
            ),
            # Un aviso de SLA por destinatario, ticket, tipo y umbral.
            models.UniqueConstraint(
                fields=["destinatario", "ticket", "tipo", "umbral"], condition=Q(tipo__in=TIPOS_SLA),
                name="notificacion_sla_unica",
            ),
            models.UniqueConstraint(
                fields=["destinatario", "hallazgo"], condition=Q(hallazgo__isnull=False),
                name="notificacion_unica_por_hallazgo",
            ),
        ]

    def __str__(self):
        return f"{self.destinatario} · {self.get_tipo_display()}"
