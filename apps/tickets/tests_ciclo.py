import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.activos.models import CoordinadorMaquina, Nivel, NodoActivo
from apps.usuarios.models import Rol, Usuario

from . import sla
from .models import CierreTecnico, ContraReporte, Estado, EventoTicket, TipoEvento
from .servicios import TransicionInvalida, acciones_permitidas, crear_ticket, transicionar

CIERRE = {
    "causa_raiz": "Rodamiento desgastado por falta de lubricación.",
    "accion_correctiva": "Se cambió el rodamiento y se lubricó el eje.",
    "repuestos": "Rodamiento 6205",
    "recomendacion_preventiva": "Lubricar cada 15 días según el plan.",
}


class Base(TestCase):
    def setUp(self):
        self.operador = Usuario.objects.create_user("op", rol=Rol.OPERADOR)
        self.coord = Usuario.objects.create_user("coord", rol=Rol.COORDINADOR)
        self.otro_coord = Usuario.objects.create_user("coord2", rol=Rol.COORDINADOR)
        self.tecnico = Usuario.objects.create_user("tec", rol=Rol.TECNICO)
        self.otro_tecnico = Usuario.objects.create_user("tec2", rol=Rol.TECNICO)
        self.maquina = NodoActivo.objects.create(nombre="Laminadora 6", nivel=Nivel.MAQUINA)
        self.unidad = NodoActivo.objects.create(nombre="Corte", nivel=Nivel.UNIDAD, padre=self.maquina)
        CoordinadorMaquina.objects.create(coordinador=self.coord, maquina=self.maquina)
        self.ticket, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.unidad, criticidad="urgente",
                                      descripcion="La cuchilla no corta parejo.", reportado_por=self.operador)

    def t(self, tipo, actor, **kw):
        self.ticket, evento = transicionar(self.ticket, tipo, actor, **kw)
        return evento


class CicloCompletoTests(Base):
    def test_todos_los_estados_con_rechazo_quedan_en_eventos(self):
        """Condición de cierre de la Fase 5."""
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        self.t(TipoEvento.INICIAR, self.tecnico)
        self.t(TipoEvento.PAUSAR, self.tecnico, comentario="Falta el repuesto en bodega.")
        self.t(TipoEvento.REANUDAR, self.coord, comentario="Ya llegó el repuesto, continúe.")
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre=CIERRE)
        self.t(TipoEvento.RECHAZAR, self.coord, comentario="Sigue cortando disparejo.")
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre={**CIERRE, "causa_raiz": "Además, la cuchilla estaba desafilada."})
        self.t(TipoEvento.VALIDAR, self.coord)

        self.assertEqual(self.ticket.estado, Estado.CERRADO)
        pasos = list(EventoTicket.objects.filter(ticket=self.ticket).values_list("tipo", "estado_desde", "estado_hacia", "actor__username"))
        self.assertEqual(pasos, [
            ("crear", "", "reportado", "op"),
            ("asignar", "reportado", "asignado", "coord"),
            ("iniciar", "asignado", "en_proceso", "tec"),
            ("pausar", "en_proceso", "en_pausa", "tec"),
            ("reanudar", "en_pausa", "en_proceso", "coord"),
            ("resolver", "en_proceso", "resuelto", "tec"),
            ("rechazar", "resuelto", "en_proceso", "coord"),
            ("resolver", "en_proceso", "resuelto", "tec"),
            ("validar", "resuelto", "cerrado", "coord"),
        ])
        # Un cierre por intento; el contra-reporte quedó respondido.
        self.assertEqual(list(CierreTecnico.objects.values_list("intento", flat=True)), [1, 2])
        contra = ContraReporte.objects.get()
        self.assertEqual((contra.respuesta, contra.respondido_por), ("Ya llegó el repuesto, continúe.", self.coord))
        # Fechas por hito.
        for campo in ("asignado_en", "iniciado_en", "resuelto_en", "cerrado_en"):
            self.assertIsNotNone(getattr(self.ticket, campo), campo)

    def test_textos_se_guardan_sin_modificar(self):
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        self.t(TipoEvento.INICIAR, self.tecnico)
        texto = {**CIERRE, "causa_raiz": "  Rodamiento DESGASTADO…\n¡sin grasa!  "}
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre=texto)
        self.assertEqual(CierreTecnico.objects.get().causa_raiz, texto["causa_raiz"])

    def test_anular(self):
        self.t(TipoEvento.ANULAR, self.coord, comentario="Duplicado del reporte #1.")
        self.assertEqual(self.ticket.estado, Estado.ANULADO)
        self.assertIsNotNone(self.ticket.anulado_en)

    def test_reasignar_y_reanuda_el_tecnico(self):
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        evento = self.t(TipoEvento.REASIGNAR, self.coord, tecnico=self.otro_tecnico)
        self.assertEqual((self.ticket.tecnico, self.ticket.estado), (self.otro_tecnico, Estado.ASIGNADO))
        self.assertIn("De tec a tec2", evento.comentario)
        self.t(TipoEvento.INICIAR, self.otro_tecnico)
        self.t(TipoEvento.PAUSAR, self.otro_tecnico, comentario="Espero que paren la línea.")
        self.t(TipoEvento.REANUDAR, self.otro_tecnico)  # el técnico reanuda sin respuesta
        self.assertEqual(self.ticket.estado, Estado.EN_PROCESO)


class ReglasTests(Base):
    def assertNoPermite(self, tipo, actor, mensaje, **kw):
        with self.assertRaisesMessage(TransicionInvalida, mensaje):
            transicionar(self.ticket, tipo, actor, **kw)

    def test_transicion_no_permitida_desde_el_estado(self):
        self.assertNoPermite(TipoEvento.INICIAR, self.tecnico, "no permite")
        self.assertNoPermite(TipoEvento.VALIDAR, self.coord, "no permite")

    def test_roles(self):
        self.assertNoPermite(TipoEvento.ASIGNAR, self.operador, "rol", tecnico=self.tecnico)
        self.assertNoPermite(TipoEvento.ASIGNAR, self.tecnico, "rol", tecnico=self.tecnico)
        self.assertNoPermite(TipoEvento.ASIGNAR, self.otro_coord, "sus máquinas", tecnico=self.tecnico)
        self.assertNoPermite(TipoEvento.ASIGNAR, self.coord, "Elija un técnico", tecnico=self.operador)
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        self.assertNoPermite(TipoEvento.INICIAR, self.otro_tecnico, "otro técnico")

    def test_textos_obligatorios(self):
        self.assertNoPermite(TipoEvento.ANULAR, self.coord, "motivo de la anulación", comentario="no")
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        self.t(TipoEvento.INICIAR, self.tecnico)
        self.assertNoPermite(TipoEvento.PAUSAR, self.tecnico, "motivo de la pausa", comentario="   ")
        self.assertNoPermite(TipoEvento.RESOLVER, self.tecnico, "causa raíz", cierre={**CIERRE, "causa_raiz": "corta"})
        self.assertNoPermite(TipoEvento.RESOLVER, self.tecnico, "recomendación",
                             cierre={**CIERRE, "recomendacion_preventiva": ""})
        self.t(TipoEvento.PAUSAR, self.tecnico, comentario="Falta el repuesto en bodega.")
        self.assertNoPermite(TipoEvento.REANUDAR, self.coord, "respuesta", comentario="ok")
        # Nada de lo rechazado dejó eventos ni cierres.
        self.assertEqual(EventoTicket.objects.count(), 4)
        self.assertEqual(CierreTecnico.objects.count(), 0)

    def test_doble_clic_no_repite(self):
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        viejo = self.ticket
        viejo.estado = Estado.REPORTADO  # copia vieja en memoria, como una pestaña sin recargar
        self.assertNoPermite(TipoEvento.ASIGNAR, self.coord, "no permite", tecnico=self.tecnico)
        self.assertEqual(EventoTicket.objects.filter(tipo=TipoEvento.ASIGNAR).count(), 1)

    def test_acciones_permitidas(self):
        self.assertEqual(acciones_permitidas(self.ticket, self.coord), [TipoEvento.ASIGNAR, TipoEvento.ANULAR])
        self.assertEqual(acciones_permitidas(self.ticket, self.tecnico), [])
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        self.assertEqual(acciones_permitidas(self.ticket, self.tecnico), [TipoEvento.INICIAR])


class SLATests(Base):
    def test_semaforo_asignar_y_resolver(self):
        reglas = sla.reglas_activas()  # urgente: asignar 2 h, resolver 24 h
        inicio = self.ticket.reportado_en
        s = sla.semaforo(self.ticket, reglas, ahora=inicio + timedelta(minutes=60))
        self.assertEqual((s.meta, s.color), ("asignar", "verde"))
        self.assertEqual(sla.semaforo(self.ticket, reglas, ahora=inicio + timedelta(minutes=90)).color, "amarillo")
        self.assertEqual(sla.semaforo(self.ticket, reglas, ahora=inicio + timedelta(minutes=121)).color, "rojo")
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        s = sla.semaforo(self.ticket, reglas, ahora=inicio + timedelta(hours=3))
        self.assertEqual((s.meta, s.color), ("resolver", "verde"))

    def test_resuelto_queda_congelado_y_cerrado_sin_semaforo(self):
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        self.t(TipoEvento.INICIAR, self.tecnico)
        self.t(TipoEvento.RESOLVER, self.tecnico, cierre=CIERRE)
        mucho_despues = timezone.now() + timedelta(days=10)
        s = sla.semaforo(self.ticket, ahora=mucho_despues)
        self.assertTrue(s.congelado)
        self.assertEqual(s.color, "verde")
        self.t(TipoEvento.VALIDAR, self.coord)
        self.assertIsNone(sla.semaforo(self.ticket))

    def test_tiempo_en_pausa(self):
        self.t(TipoEvento.ASIGNAR, self.coord, tecnico=self.tecnico)
        self.t(TipoEvento.INICIAR, self.tecnico)
        self.t(TipoEvento.PAUSAR, self.tecnico, comentario="Falta el repuesto en bodega.")
        pausa = EventoTicket.objects.get(tipo=TipoEvento.PAUSAR)
        EventoTicket.objects.filter(pk=pausa.pk).update(fecha=pausa.fecha - timedelta(minutes=45))
        self.t(TipoEvento.REANUDAR, self.tecnico)
        self.assertAlmostEqual(sla.tiempo_en_pausa(self.ticket).total_seconds(), 45 * 60, delta=5)

    def test_duracion(self):
        self.assertEqual([sla.duracion(timedelta(minutes=m)) for m in (5, 125, 60 * 26)], ["5 min", "2 h 05 min", "1 d 2 h"])
