from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.activos.models import NodoActivo


class Criticidad(models.TextChoices):
    CRITICA = "critica", "Crítica"
    URGENTE = "urgente", "Urgente"
    IMPORTANTE = "importante", "Importante"


class Estado(models.TextChoices):
    REPORTADO = "reportado", "Reportado"
    ASIGNADO = "asignado", "Asignado"
    EN_PROCESO = "en_proceso", "En proceso"
    EN_PAUSA = "en_pausa", "En pausa"
    RESUELTO = "resuelto", "Resuelto (pendiente de validación)"
    CERRADO = "cerrado", "Cerrado"
    ANULADO = "anulado", "Anulado"


class TipoEvento(models.TextChoices):
    CREAR = "crear", "Reporte creado"
    ASIGNAR = "asignar", "Asignado a técnico"
    INICIAR = "iniciar", "Trabajo iniciado"
    PAUSAR = "pausar", "Pausado (contra-reporte)"
    REANUDAR = "reanudar", "Reanudado"
    RESOLVER = "resolver", "Resuelto"
    VALIDAR = "validar", "Validado y cerrado"
    RECHAZAR = "rechazar", "Cierre rechazado"
    ANULAR = "anular", "Anulado"


def formato_minutos(minutos):
    """30 → '30 min', 120 → '2 h', 90 → '1 h 30 min'."""
    horas, resto = divmod(minutos, 60)
    if not horas:
        return f"{resto} min"
    return f"{horas} h" + (f" {resto} min" if resto else "")


class ReglaSLA(models.Model):
    """Tiempos por criticidad, en minutos. Solo una regla activa por criticidad."""

    criticidad = models.CharField("criticidad", max_length=20, choices=Criticidad.choices)
    minutos_para_asignar = models.PositiveIntegerField("minutos para asignar")
    minutos_para_resolver = models.PositiveIntegerField("minutos para resolver")
    modificada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="modificada por",
    )
    modificada_en = models.DateTimeField("modificada en", auto_now=True)
    activa = models.BooleanField("activa", default=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "regla SLA"
        verbose_name_plural = "reglas SLA"
        constraints = [
            models.UniqueConstraint(fields=["criticidad"], condition=Q(activa=True), name="una_regla_activa_por_criticidad"),
        ]

    def __str__(self):
        return (f"{self.get_criticidad_display()}: asignar {formato_minutos(self.minutos_para_asignar)}, "
                f"resolver {formato_minutos(self.minutos_para_resolver)}")


class Ticket(models.Model):
    """El estado solo cambia por la función de servicio de transiciones (Fase 5), nunca desde las vistas."""

    uuid_cliente = models.UUIDField("UUID del cliente", unique=True)
    nodo = models.ForeignKey(NodoActivo, on_delete=models.PROTECT, related_name="tickets", verbose_name="activo")
    descripcion = models.TextField("descripción")
    criticidad = models.CharField("criticidad", max_length=20, choices=Criticidad.choices)
    estado = models.CharField("estado", max_length=20, choices=Estado.choices, default=Estado.REPORTADO)
    reportado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets_reportados",
        verbose_name="reportado por",
    )
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="tickets_asignados", verbose_name="técnico",
    )
    # Fechas por hito. El detalle completo (pausas, rechazos) está en EventoTicket.
    reportado_en = models.DateTimeField("reportado en", default=timezone.now)
    asignado_en = models.DateTimeField("asignado en", null=True, blank=True)
    iniciado_en = models.DateTimeField("iniciado en", null=True, blank=True)
    resuelto_en = models.DateTimeField("resuelto en", null=True, blank=True)
    cerrado_en = models.DateTimeField("cerrado en", null=True, blank=True)
    anulado_en = models.DateTimeField("anulado en", null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "ticket"
        verbose_name_plural = "tickets"
        ordering = ["-reportado_en"]
        indexes = [models.Index(fields=["estado", "criticidad"])]

    def __str__(self):
        return f"#{self.pk} · {self.nodo.nombre} · {self.get_estado_display()}"


class EventoTicket(models.Model):
    """Línea de tiempo del ticket: un registro por cada transición."""

    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="eventos", verbose_name="ticket")
    tipo = models.CharField("tipo", max_length=20, choices=TipoEvento.choices)
    estado_desde = models.CharField("estado desde", max_length=20, choices=Estado.choices, blank=True)
    estado_hacia = models.CharField("estado hacia", max_length=20, choices=Estado.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="actor")
    comentario = models.TextField("comentario", blank=True)
    fecha = models.DateTimeField("fecha", default=timezone.now)

    class Meta:
        verbose_name = "evento de ticket"
        verbose_name_plural = "eventos de tickets"
        ordering = ["fecha", "pk"]

    def __str__(self):
        return f"#{self.ticket_id} · {self.get_tipo_display()}"


class CierreTecnico(models.Model):
    """Un registro por intento: si el coordinador rechaza, el técnico escribe un cierre nuevo."""

    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="cierres", verbose_name="ticket")
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="técnico")
    intento = models.PositiveSmallIntegerField("intento")
    causa_raiz = models.TextField("causa raíz")
    accion_correctiva = models.TextField("acción correctiva")
    repuestos = models.TextField("repuestos", blank=True)
    recomendacion_preventiva = models.TextField("recomendación preventiva")
    creado_en = models.DateTimeField("creado en", default=timezone.now)

    class Meta:
        verbose_name = "cierre técnico"
        verbose_name_plural = "cierres técnicos"
        ordering = ["ticket", "intento"]
        constraints = [models.UniqueConstraint(fields=["ticket", "intento"], name="cierre_unico_por_intento")]

    def __str__(self):
        return f"#{self.ticket_id} · intento {self.intento}"


class ContraReporte(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name="contra_reportes", verbose_name="ticket")
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="técnico")
    motivo = models.TextField("motivo")
    fecha = models.DateTimeField("fecha", default=timezone.now)
    respuesta = models.TextField("respuesta del coordinador", blank=True)
    respondido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="respondido por",
    )
    respondido_en = models.DateTimeField("respondido en", null=True, blank=True)

    class Meta:
        verbose_name = "contra-reporte"
        verbose_name_plural = "contra-reportes"
        ordering = ["-fecha"]

    def __str__(self):
        return f"#{self.ticket_id} · {timezone.localtime(self.fecha):%Y-%m-%d %H:%M}"
