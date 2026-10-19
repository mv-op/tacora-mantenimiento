import time
import uuid

from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from simple_history.admin import SimpleHistoryAdmin

from . import importacion, servicios
from .models import CoordinadorMaquina, EstadoCuraduria, NodoActivo

CARPETA_IMPORTACIONES = settings.DATA_DIR / "importaciones"


class HijosInline(admin.TabularInline):
    model = NodoActivo
    fk_name = "padre"
    fields = ["nombre", "nivel", "origen", "estado_curaduria", "is_active"]
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name_plural = "hijos"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(NodoActivo)
class NodoActivoAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "nivel", "ruta", "origen", "estado_curaduria", "is_active"]
    list_filter = ["nivel", "origen", "estado_curaduria", "is_active"]
    search_fields = ["nombre", "nombre_normalizado"]
    autocomplete_fields = ["padre"]
    readonly_fields = ["ruta", "nombre_normalizado", "fusionado_en", "creado_por", "creado_en", "actualizado_en"]
    fields = ["nombre", "nivel", "padre", "ruta", "nombre_normalizado", "origen", "estado_curaduria", "is_active",
              "fusionado_en", "creado_por", "creado_en", "actualizado_en"]
    inlines = [HijosInline]
    actions = ["aprobar", "desactivar", "fusionar_nodos"]
    change_list_template = "admin/activos/nodoactivo/change_list.html"

    def has_delete_permission(self, request, obj=None):
        return False  # Los nodos nunca se borran.

    def get_urls(self):
        propias = [
            path("plantilla/", self.admin_site.admin_view(self.vista_plantilla), name="activos_plantilla"),
            path("importar/", self.admin_site.admin_view(self.vista_importar), name="activos_importar"),
            path("arbol/", self.admin_site.admin_view(self.vista_arbol), name="activos_arbol"),
        ]
        return propias + super().get_urls()

    def vista_plantilla(self, request):
        respuesta = HttpResponse(
            importacion.generar_plantilla(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        respuesta["Content-Disposition"] = 'attachment; filename="plantilla_arbol_activos.xlsx"'
        return respuesta

    def vista_importar(self, request):
        """Paso 1: subir y revisar (no guarda). Paso 2: confirmar (vuelve a analizar e importa)."""
        if not self.has_add_permission(request):
            return redirect("admin:activos_nodoactivo_changelist")
        contexto = {**self.admin_site.each_context(request), "opts": self.model._meta, "title": "Importar árbol desde Excel"}

        if request.method == "POST" and "archivo" in request.FILES:
            CARPETA_IMPORTACIONES.mkdir(parents=True, exist_ok=True)
            # Limpia archivos de revisiones que nunca se confirmaron.
            for viejo in CARPETA_IMPORTACIONES.glob("*.xlsx"):
                if time.time() - viejo.stat().st_mtime > 24 * 3600:
                    viejo.unlink(missing_ok=True)
            token = uuid.uuid4().hex
            ruta = CARPETA_IMPORTACIONES / f"{token}.xlsx"
            with open(ruta, "wb") as destino:
                for trozo in request.FILES["archivo"].chunks():
                    destino.write(trozo)
            contexto.update(resultado=importacion.analizar(ruta), token=token,
                            nombre_archivo=request.FILES["archivo"].name)
            if contexto["resultado"].errores:
                ruta.unlink(missing_ok=True)
            return TemplateResponse(request, "admin/activos/nodoactivo/importar.html", contexto)

        if request.method == "POST" and "token" in request.POST:
            token = request.POST["token"]
            ruta = CARPETA_IMPORTACIONES / f"{token}.xlsx"
            if not token.isalnum() or not ruta.exists():
                self.message_user(request, "El archivo ya no está disponible. Súbalo de nuevo.", messages.ERROR)
                return redirect("admin:activos_importar")
            resultado = importacion.analizar(ruta)  # Se analiza otra vez por si el árbol cambió.
            if resultado.errores:
                contexto.update(resultado=resultado, nombre_archivo="")
                ruta.unlink(missing_ok=True)
                return TemplateResponse(request, "admin/activos/nodoactivo/importar.html", contexto)
            creados = importacion.importar(resultado, request.user)
            ruta.unlink(missing_ok=True)
            self.message_user(request, f"Importación terminada: {creados} nodos nuevos.", messages.SUCCESS)
            return redirect("admin:activos_arbol")

        return TemplateResponse(request, "admin/activos/nodoactivo/importar.html", contexto)

    def vista_arbol(self, request):
        nodos = list(NodoActivo.objects.filter(is_active=True).order_by("nombre"))
        hijos = {}
        for nodo in nodos:
            hijos.setdefault(nodo.padre_id, []).append(nodo)
        for nodo in nodos:
            nodo.lista_hijos = hijos.get(nodo.pk, [])
        con_coordinador = set(CoordinadorMaquina.objects.values_list("maquina", flat=True))
        contexto = {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": "Árbol de activos",
            "maquinas": hijos.get(None, []), "total": len(nodos),
            "pendientes": sum(n.estado_curaduria == EstadoCuraduria.PENDIENTE for n in nodos),
            # Los reportes de estas máquinas no le llegan a ningún coordinador.
            "sin_coordinador": [m for m in hijos.get(None, []) if m.pk not in con_coordinador],
        }
        return TemplateResponse(request, "admin/activos/nodoactivo/arbol.html", contexto)

    def save_model(self, request, obj, form, change):
        if not change and not obj.creado_por_id:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Aprobar curaduría")
    def aprobar(self, request, queryset):
        for nodo in queryset.filter(estado_curaduria=EstadoCuraduria.PENDIENTE):
            nodo.estado_curaduria = EstadoCuraduria.APROBADO
            nodo.save()  # save() uno a uno para que quede en el historial.
        self.message_user(request, "Nodos aprobados.", messages.SUCCESS)

    @admin.action(description="Fusionar nodos duplicados…")
    def fusionar_nodos(self, request, queryset):
        """Paso 1: elegir el nodo correcto entre los seleccionados. Paso 2: fusionar los demás en él."""
        nodos = list(queryset.filter(is_active=True).select_related("padre"))
        if len(nodos) < 2:
            self.message_user(request, "Seleccione al menos dos nodos activos para fusionar.", messages.ERROR)
            return None
        if len({n.nivel for n in nodos}) > 1:
            self.message_user(request, "Solo se fusionan nodos del mismo nivel.", messages.ERROR)
            return None

        if "correcto" in request.POST:
            correcto = next((n for n in nodos if str(n.pk) == request.POST["correcto"]), None)
            if correcto is None:
                self.message_user(request, "Elija cuál es el nodo correcto.", messages.ERROR)
                return None
            total = {"tickets": 0, "hijos_movidos": 0, "hijos_fusionados": 0}
            for duplicado in nodos:
                if duplicado.pk != correcto.pk:
                    duplicado.refresh_from_db()  # una fusión anterior pudo cambiarlo
                    if duplicado.is_active:
                        servicios.fusionar(correcto, duplicado, total)
            self.message_user(
                request,
                f"Fusionados en «{correcto.ruta}»: {total['tickets']} tickets y {total['hijos_movidos']} hijos movidos, "
                f"{total['hijos_fusionados']} hijos con el mismo nombre fusionados.",
                messages.SUCCESS,
            )
            return None

        for nodo in nodos:
            nodo.num_tickets = nodo.tickets.count()
            nodo.num_hijos = nodo.hijos.filter(is_active=True).count()
        contexto = {
            **self.admin_site.each_context(request), "opts": self.model._meta, "title": "Fusionar nodos duplicados",
            "nodos": nodos, "accion": "fusionar_nodos",
            "seleccionados": request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME),
        }
        return TemplateResponse(request, "admin/activos/nodoactivo/fusionar.html", contexto)

    @admin.action(description="Desactivar (no se borra)")
    def desactivar(self, request, queryset):
        for nodo in queryset.filter(is_active=True):
            nodo.is_active = False
            nodo.save()
        self.message_user(request, "Nodos desactivados.", messages.SUCCESS)


@admin.register(CoordinadorMaquina)
class CoordinadorMaquinaAdmin(admin.ModelAdmin):
    list_display = ["coordinador", "maquina"]
    list_filter = ["coordinador"]
    autocomplete_fields = ["maquina"]
