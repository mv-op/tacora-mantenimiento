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
    TICKET_REASIGNADO = "ticket_reasignado", "Ticket reasignado a otro técnico"
    TRABAJO_INICIADO = "trabajo_iniciado", "Técnico inicia trabajo"
    CONTRA_REPORTE = "contra_reporte", "Contra-reporte"
    RESPUESTA_CONTRA_REPORTE = "respuesta_contra_reporte", "Respuesta a contra-reporte"
    RESUELTO_PENDIENTE = "resuelto_pendiente", "Resuelto, pendiente de validar"
    CIERRE_RECHAZADO = "cierre_rechazado", "Cierre rechazado"
    TICKET_CERRADO = "ticket_cerrado", "Ticket cerrado"
    TICKET_ANULADO = "ticket_anulado", "Reporte anulado"
    SLA_POR_VENCER = "sla_por_vencer", "Plazo por vencer"
    SLA_VENCIDO = "sla_vencido", "Plazo vencido"
    NODO_PENDIENTE = "nodo_pendiente", "Nodo nuevo pendiente de curaduría"
    HALLAZGO_AGENTE = "hallazgo_agente", "Hallazgo del agente"


TIPOS_SLA = [TipoNotificacion.SLA_POR_VENCER, TipoNotificacion.SLA_VENCIDO]

# Color de cada tipo: (tarjeta con borde, punto/etiqueta). Clases completas para que Tailwind las encuentre.
T = TipoNotificacion
ESTILOS = {
    T.NUEVO_REPORTE: {"tarjeta": "border-blue-500 bg-blue-50", "etiqueta": "bg-blue-600 text-white"},
    T.REPORTE_CRITICO: {"tarjeta": "border-red-600 bg-red-50", "etiqueta": "bg-red-600 text-white"},
    T.TICKET_ASIGNADO: {"tarjeta": "border-indigo-500 bg-indigo-50", "etiqueta": "bg-indigo-600 text-white"},
    T.TICKET_REASIGNADO: {"tarjeta": "border-indigo-500 bg-indigo-50", "etiqueta": "bg-indigo-600 text-white"},
    T.TRABAJO_INICIADO: {"tarjeta": "border-amber-500 bg-amber-50", "etiqueta": "bg-amber-500 text-white"},
    T.CONTRA_REPORTE: {"tarjeta": "border-orange-500 bg-orange-50", "etiqueta": "bg-orange-500 text-white"},
    T.RESPUESTA_CONTRA_REPORTE: {"tarjeta": "border-orange-500 bg-orange-50", "etiqueta": "bg-orange-500 text-white"},
    T.RESUELTO_PENDIENTE: {"tarjeta": "border-teal-500 bg-teal-50", "etiqueta": "bg-teal-600 text-white"},
    T.CIERRE_RECHAZADO: {"tarjeta": "border-rose-600 bg-rose-50", "etiqueta": "bg-rose-600 text-white"},
    T.TICKET_CERRADO: {"tarjeta": "border-green-600 bg-green-50", "etiqueta": "bg-green-600 text-white"},
    T.TICKET_ANULADO: {"tarjeta": "border-slate-400 bg-slate-50", "etiqueta": "bg-slate-500 text-white"},
    T.SLA_POR_VENCER: {"tarjeta": "border-yellow-400 bg-yellow-50", "etiqueta": "bg-yellow-400 text-yellow-950"},
    T.SLA_VENCIDO: {"tarjeta": "border-red-700 bg-red-100", "etiqueta": "bg-red-700 text-white"},
    T.NODO_PENDIENTE: {"tarjeta": "border-violet-500 bg-violet-50", "etiqueta": "bg-violet-600 text-white"},
    T.HALLAZGO_AGENTE: {"tarjeta": "border-fuchsia-500 bg-fuchsia-50", "etiqueta": "bg-fuchsia-600 text-white"},
}
ESTILO_POR_DEFECTO = {"tarjeta": "border-slate-400 bg-white", "etiqueta": "bg-slate-500 text-white"}


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
    # Avisos de SLA: a qué plazo se refieren (asignar o resolver) y en qué punto (70 % o 100 %).
    etapa = models.CharField("etapa del SLA", max_length=10, blank=True)
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
            # Un aviso de SLA por destinatario, ticket, plazo (asignar/resolver) y umbral.
            models.UniqueConstraint(
                fields=["destinatario", "ticket", "etapa", "umbral"], condition=Q(tipo__in=TIPOS_SLA),
                name="notificacion_sla_unica",
            ),
            models.UniqueConstraint(
                fields=["destinatario", "hallazgo"], condition=Q(hallazgo__isnull=False),
                name="notificacion_unica_por_hallazgo",
            ),
        ]

    def __str__(self):
        return f"{self.destinatario} · {self.get_tipo_display()}"

    @property
    def estilo(self):
        return ESTILOS.get(self.tipo, ESTILO_POR_DEFECTO)
