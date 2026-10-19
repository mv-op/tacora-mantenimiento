"""Cada fila de la matriz «Quién recibe qué» del plan, más reporte anulado y reasignado (condición de cierre Fase 6)."""

import time
import uuid
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.db.models import F
from django.test import TestCase

from apps.activos.models import CoordinadorMaquina, Nivel, NodoActivo
from apps.activos.servicios import crear_nodo_operador
from apps.tickets.models import Ticket, TipoEvento
from apps.tickets.servicios import crear_ticket, transicionar
from apps.usuarios import acceso
from apps.usuarios.models import AceptacionTerminos, Rol, Usuario

from .models import Notificacion, Prioridad, TipoNotificacion as T

CIERRE = {
    "causa_raiz": "Rodamiento desgastado por falta de lubricación.",
    "accion_correctiva": "Se cambió el rodamiento y se lubricó el eje.",
    "recomendacion_preventiva": "Lubricar cada 15 días según el plan.",
}


def usuario(username, rol):
    u = Usuario.objects.create_user(username, password="x", rol=rol, debe_cambiar_clave=False, nombre_visible=username)
    AceptacionTerminos.objects.create(usuario=u, version=settings.TERMINOS_VERSION)
    return u


class Base(TestCase):
    def setUp(self):
        self.operador = usuario("operador", Rol.OPERADOR)
        self.produccion = usuario("produccion", Rol.COORDINADOR)
        self.mantenimiento = usuario("mantenimiento", Rol.COORDINADOR)
        self.ajeno = usuario("coord_ajeno", Rol.COORDINADOR)
        self.tecnico = usuario("tecnico", Rol.TECNICO)
        self.admin = usuario("admin2", Rol.ADMIN)
        self.maquina = NodoActivo.objects.create(nombre="Laminadora 6", nivel=Nivel.MAQUINA)
        self.unidad = NodoActivo.objects.create(nombre="Corte", nivel=Nivel.UNIDAD, padre=self.maquina)
        otra = NodoActivo.objects.create(nombre="Extrusora", nivel=Nivel.MAQUINA)
        for coord in (self.produccion, self.mantenimiento):
            CoordinadorMaquina.objects.create(coordinador=coord, maquina=self.maquina)
        CoordinadorMaquina.objects.create(coordinador=self.ajeno, maquina=otra)

    def reportar(self, criticidad="urgente"):
        self.ticket, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.unidad, criticidad=criticidad,
                                      descripcion="La cuchilla no corta parejo.", reportado_por=self.operador)
        return self.ticket

    def t(self, tipo, actor, **kw):
        self.ticket, _ = transicionar(self.ticket, tipo, actor, **kw)

    def avisos(self, tipo):
        """{usuario: prioridad} de los avisos de ese tipo."""
        return {n.destinatario.username: n.prioridad for n in Notificacion.objects.filter(tipo=tipo)}

    def hasta_en_proceso(self):
        self.reportar()
        self.t(TipoEvento.ASIGNAR, self.produccion, tecnico=self.tecnico)
        self.t(TipoEvento.INICIAR, self.tecnico)


class MatrizTests(Base):
    def test_nuevo_reporte_a_los_coordinadores_de_la_maquina(self):
        self.reportar()
        self.assertEqual(self.avisos(T.NUEVO_REPORTE), {"produccion": Prioridad.NORMAL, "mantenimiento": Prioridad.NORMAL})

    def test_reporte_critico_con_sonido(self):
        self.reportar("critica")
        self.assertEqual(self.avisos(T.REPORTE_CRITICO), {"produccion": Prioridad.ALTA, "mantenimiento": Prioridad.ALTA})
        self.assertEqual(self.avisos(T.NUEVO_REPORTE), {})

    def test_ticket_asignado_al_operador_y_al_tecnico(self):
        self.reportar()
        self.t(TipoEvento.ASIGNAR, self.produccion, tecnico=self.tecnico)
        self.assertEqual(set(self.avisos(T.TICKET_ASIGNADO)), {"operador", "tecnico"})

    def test_tecnico_inicia_al_operador(self):
        self.hasta_en_proceso()
        self.assertEqual(set(self.avisos(T.TRABAJO_INICIADO)), {"operador"})

    def test_contra_reporte_a_los_coordinadores(self):
        self.hasta_en_proceso()
        self.t(TipoEvento.PAUSAR, self.tecnico, comentario="Falta el repuesto en bodega.")
        self.assertEqual(set(self.avisos(T.CONTRA_REPORTE)), {"produccion", "mantenimiento"})
        self.assertIn("Falta el repuesto", Notificacion.objects.filter(tipo=T.CONTRA_REPORTE).first().mensaje)

    def test_respuesta_a_contra_reporte_al_tecnico(self):
        self.hasta_en_proceso()
        self.t(TipoEvento.PAUSAR, self.tecnico, comentario="Falta el repuesto en bodega.")
        self.t(TipoEvento.REANUDAR, self.mantenimiento, comentario="Ya llegó, continúe por favor.")
        self.assertEqual(set(self.avisos(T.RESPUESTA_CONTRA_REPORTE)), {"tecnico"})

    def test_resuelto_al_operador_y_coordinadores(self):
        self.hasta_en_proceso()
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre=CIERRE)
        self.assertEqual(set(self.avisos(T.RESUELTO_PENDIENTE)), {"operador", "produccion", "mantenimiento"})

    def test_cierre_rechazado_al_tecnico_con_motivo(self):
        self.hasta_en_proceso()
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre=CIERRE)
        self.t(TipoEvento.RECHAZAR, self.produccion, comentario="Sigue cortando disparejo.")
        self.assertEqual(set(self.avisos(T.CIERRE_RECHAZADO)), {"tecnico"})
        self.assertIn("Sigue cortando disparejo.", Notificacion.objects.get(tipo=T.CIERRE_RECHAZADO).mensaje)
        # Un segundo rechazo vuelve a avisar.
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre=CIERRE)
        self.t(TipoEvento.RECHAZAR, self.produccion, comentario="Todavía hay rebabas.")
        self.assertEqual(Notificacion.objects.filter(tipo=T.CIERRE_RECHAZADO).count(), 2)

    def test_ticket_cerrado_al_operador_y_tecnico(self):
        self.hasta_en_proceso()
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre=CIERRE)
        self.t(TipoEvento.VALIDAR, self.produccion)
        self.assertEqual(set(self.avisos(T.TICKET_CERRADO)), {"operador", "tecnico"})

    def test_nodo_pendiente_al_administrador(self):
        crear_nodo_operador(self.unidad, "Hidráulico", self.operador)
        self.assertEqual(set(self.avisos(T.NODO_PENDIENTE)), {"admin2"})

    def test_reporte_anulado_al_operador(self):
        self.reportar()
        self.t(TipoEvento.ANULAR, self.produccion, comentario="Duplicado del reporte anterior.")
        self.assertEqual(set(self.avisos(T.TICKET_ANULADO)), {"operador"})
        self.assertIn("Duplicado", Notificacion.objects.get(tipo=T.TICKET_ANULADO).mensaje)

    def test_reasignado_al_tecnico_anterior_y_asignado_al_nuevo(self):
        nuevo = usuario("tecnico2", Rol.TECNICO)
        self.reportar()
        self.t(TipoEvento.ASIGNAR, self.produccion, tecnico=self.tecnico)
        self.t(TipoEvento.REASIGNAR, self.produccion, tecnico=nuevo)
        self.assertEqual(set(self.avisos(T.TICKET_REASIGNADO)), {"tecnico"})
        self.assertIn("tecnico2", set(self.avisos(T.TICKET_ASIGNADO)))

    def test_asignado_critico_suena_al_tecnico(self):
        self.reportar("critica")
        self.t(TipoEvento.ASIGNAR, self.produccion, tecnico=self.tecnico)
        self.assertEqual(self.avisos(T.TICKET_ASIGNADO)["tecnico"], Prioridad.ALTA)

    def test_no_se_avisa_a_quien_hizo_la_accion(self):
        # El coordinador reporta en su propia máquina: avisa al otro coordinador, no a sí mismo.
        crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.unidad, criticidad="urgente",
                     descripcion="Lo vi yo mismo en la ronda.", reportado_por=self.produccion)
        self.assertEqual(set(self.avisos(T.NUEVO_REPORTE)), {"mantenimiento"})

    def test_coordinador_de_otra_maquina_no_recibe_nada(self):
        self.hasta_en_proceso()
        self.assertFalse(Notificacion.objects.filter(destinatario=self.ajeno).exists())


class SLATests(Base):
    def correr(self):
        salida = StringIO()
        call_command("revisar_sla", stdout=salida)
        return salida.getvalue()

    def envejecer(self, minutos):
        Ticket.objects.filter(pk=self.ticket.pk).update(reportado_en=F("reportado_en") - timedelta(minutes=minutos))

    def test_por_vencer_y_vencido_sin_repetir(self):
        self.reportar()  # urgente: asignar en 2 h
        self.assertIn("0 avisos", self.correr())
        self.envejecer(90)  # 75 % del plazo para asignar
        self.correr()
        self.correr()  # la tarea corre cada 5 min: no repite
        self.assertEqual(self.avisos(T.SLA_POR_VENCER), {"produccion": Prioridad.NORMAL, "mantenimiento": Prioridad.NORMAL})
        self.envejecer(40)  # vencido
        self.correr()
        self.assertEqual(self.avisos(T.SLA_VENCIDO), {"produccion": Prioridad.ALTA, "mantenimiento": Prioridad.ALTA})

    def test_tecnico_recibe_sla_del_plazo_de_resolver(self):
        self.reportar()
        self.t(TipoEvento.ASIGNAR, self.produccion, tecnico=self.tecnico)
        self.envejecer(60 * 20)  # 20 h de 24 h para resolver
        self.correr()
        aviso = Notificacion.objects.get(destinatario=self.tecnico, tipo=T.SLA_POR_VENCER)
        self.assertEqual((aviso.etapa, aviso.umbral), ("resolver", 70))

    def test_asignar_y_resolver_son_avisos_distintos(self):
        self.reportar()
        self.envejecer(100)
        self.correr()  # por vencer: asignar
        self.t(TipoEvento.ASIGNAR, self.produccion, tecnico=self.tecnico)
        self.envejecer(60 * 20)
        self.correr()  # por vencer: resolver
        self.assertEqual(sorted(Notificacion.objects.filter(destinatario=self.produccion, tipo=T.SLA_POR_VENCER)
                                .values_list("etapa", flat=True)), ["asignar", "resolver"])


class PantallasTests(Base):
    def test_campana_estado_y_abrir(self):
        self.reportar("critica")
        self.client.force_login(self.produccion)
        r = self.client.get("/bandeja/")
        self.assertContains(r, 'id="campana-contador"')
        self.assertEqual(r.context["campana_sin_leer"], 1)

        datos = self.client.get("/notificaciones/estado/?despues=0").json()
        self.assertEqual(datos["sin_leer"], 1)
        self.assertEqual(len(datos["fijas"]), 1)
        self.assertTrue(datos["nuevas"][0]["alta"])
        self.assertIn("border-red-600", datos["nuevas"][0]["tarjeta"])  # color del reporte crítico

        aviso = Notificacion.objects.get(destinatario=self.produccion)
        r = self.client.get(f"/notificaciones/{aviso.pk}/abrir/")
        self.assertRedirects(r, f"/bandeja/{self.ticket.pk}/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/notificaciones/estado/?despues=0").json()["sin_leer"], 0)

    def test_visto_y_marcar_todas(self):
        self.reportar()
        self.reportar()
        self.client.force_login(self.produccion)
        primera = Notificacion.objects.filter(destinatario=self.produccion).first()
        self.assertEqual(self.client.post(f"/notificaciones/{primera.pk}/vista/").status_code, 204)
        self.assertContains(self.client.get("/notificaciones/"), "Marcar todas como leídas")
        self.client.post("/notificaciones/leer-todas/")
        self.assertFalse(Notificacion.objects.filter(destinatario=self.produccion, leida_en__isnull=True).exists())

    def test_solo_ve_las_suyas(self):
        self.reportar()
        ajena = Notificacion.objects.filter(destinatario=self.produccion).first()
        self.client.force_login(self.mantenimiento)
        self.assertEqual(self.client.get(f"/notificaciones/{ajena.pk}/abrir/").status_code, 404)

    def test_consulta_automatica_no_mantiene_viva_la_sesion(self):
        self.client.force_login(self.produccion)
        self.client.get("/bandeja/")
        sesion = self.client.session
        hace_un_minuto = int(time.time()) - 60
        sesion[acceso.CLAVE_ACTIVIDAD] = hace_un_minuto
        sesion.save()
        self.client.get("/notificaciones/estado/?despues=0", HTTP_X_CONSULTA_AUTOMATICA="1")
        self.assertEqual(self.client.session[acceso.CLAVE_ACTIVIDAD], hace_un_minuto)

    def test_cada_quien_llega_a_su_pantalla(self):
        self.reportar()
        self.t(TipoEvento.ASIGNAR, self.produccion, tecnico=self.tecnico)
        for persona, destino in [(self.tecnico, f"/ordenes/{self.ticket.pk}/"),
                                 (self.operador, f"/reportes/{self.ticket.pk}/")]:
            aviso = Notificacion.objects.get(destinatario=persona, tipo=T.TICKET_ASIGNADO)
            self.client.force_login(persona)
            self.assertRedirects(self.client.get(f"/notificaciones/{aviso.pk}/abrir/"), destino,
                                 fetch_redirect_response=False)
