import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.activos.models import Nivel, NodoActivo
from apps.tickets.models import EventoTicket, Ticket
from apps.usuarios.models import Usuario

from .models import Notificacion, TipoNotificacion


class DeduplicacionTests(TestCase):
    def setUp(self):
        self.u = Usuario.objects.create_user("coord")
        nodo = NodoActivo.objects.create(nombre="M1", nivel=Nivel.MAQUINA)
        self.t = Ticket.objects.create(uuid_cliente=uuid.uuid4(), nodo=nodo, descripcion="x",
                                       criticidad="critica", reportado_por=self.u)

    def crear(self, **kw):
        return Notificacion.objects.create(destinatario=self.u, ticket=self.t, mensaje="m", **kw)

    def test_sla_un_aviso_por_umbral(self):
        self.crear(tipo=TipoNotificacion.SLA_POR_VENCER, umbral=70)
        self.crear(tipo=TipoNotificacion.SLA_VENCIDO, umbral=100)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear(tipo=TipoNotificacion.SLA_POR_VENCER, umbral=70)

    def test_rechazos_repetidos_si_avisan(self):
        for _ in range(2):
            ev = EventoTicket.objects.create(ticket=self.t, tipo="rechazar", estado_desde="resuelto",
                                             estado_hacia="en_proceso", actor=self.u)
            self.crear(tipo=TipoNotificacion.CIERRE_RECHAZADO, evento=ev)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear(tipo=TipoNotificacion.CIERRE_RECHAZADO, evento=ev)
