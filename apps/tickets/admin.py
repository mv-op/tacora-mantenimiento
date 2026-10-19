from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import CierreTecnico, ContraReporte, EventoTicket, ReglaSLA, Ticket, formato_minutos


class SoloLecturaInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class EventoInline(SoloLecturaInline):
    model = EventoTicket
    fields = ["fecha", "tipo", "estado_desde", "estado_hacia", "actor", "comentario"]


class CierreInline(SoloLecturaInline):
    model = CierreTecnico
    fields = ["intento", "tecnico", "causa_raiz", "accion_correctiva", "repuestos", "recomendacion_preventiva", "creado_en"]


class ContraReporteInline(SoloLecturaInline):
    model = ContraReporte
    fields = ["fecha", "tecnico", "motivo", "respuesta", "respondido_por", "respondido_en"]


@admin.register(ReglaSLA)
class ReglaSLAAdmin(SimpleHistoryAdmin):
    list_display = ["criticidad", "para_asignar", "para_resolver", "activa", "modificada_por", "modificada_en"]
    list_filter = ["activa"]
    readonly_fields = ["modificada_por", "modificada_en"]

    def save_model(self, request, obj, form, change):
        obj.modificada_por = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="asignar antes de")
    def para_asignar(self, obj):
        return formato_minutos(obj.minutos_para_asignar)

    @admin.display(description="resolver antes de")
    def para_resolver(self, obj):
        return formato_minutos(obj.minutos_para_resolver)


@admin.register(Ticket)
class TicketAdmin(SimpleHistoryAdmin):
    """Los tickets se crean y cambian de estado desde la app, no desde el admin."""

    list_display = ["id", "nodo", "criticidad", "estado", "reportado_por", "tecnico", "reportado_en"]
    list_filter = ["estado", "criticidad"]
    search_fields = ["descripcion", "nodo__nombre"]
    readonly_fields = ["uuid_cliente", "nodo", "descripcion", "criticidad", "estado", "reportado_por", "tecnico",
                       "reportado_en", "asignado_en", "iniciado_en", "resuelto_en", "cerrado_en", "anulado_en"]
    inlines = [EventoInline, CierreInline, ContraReporteInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EventoTicket)
class EventoTicketAdmin(admin.ModelAdmin):
    list_display = ["fecha", "ticket", "tipo", "estado_desde", "estado_hacia", "actor"]
    list_filter = ["tipo"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
