"""Revisa los SLA de los tickets abiertos y avisa al 70 % (por vencer) y al 100 % (vencido).

En el servidor lo ejecuta un timer de systemd cada 5 minutos. En local:
    python manage.py revisar_sla            (una vez)
    python manage.py revisar_sla --repetir  (cada 5 minutos, hasta Ctrl + C)
"""

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notificaciones.servicios import notificar_sla
from apps.tickets import sla
from apps.tickets.models import Estado, Ticket

ESTADOS_CON_RELOJ = [Estado.REPORTADO, Estado.ASIGNADO, Estado.EN_PROCESO, Estado.EN_PAUSA]


class Command(BaseCommand):
    help = "Avisa los SLA por vencer (70 %) y vencidos (100 %)."

    def add_arguments(self, parser):
        parser.add_argument("--repetir", action="store_true", help="Repetir cada --cada segundos.")
        parser.add_argument("--cada", type=int, default=300, help="Segundos entre revisiones (por defecto 300).")

    def handle(self, *args, **opciones):
        while True:
            self.revisar()
            if not opciones["repetir"]:
                return
            time.sleep(opciones["cada"])

    def revisar(self):
        reglas = sla.reglas_activas()
        ahora = timezone.now()
        avisos = 0
        tickets = Ticket.objects.filter(estado__in=ESTADOS_CON_RELOJ).select_related("nodo", "tecnico")
        for ticket in tickets:
            avisos += len(notificar_sla(ticket, sla.semaforo(ticket, reglas, ahora)))
        self.stdout.write(f"{timezone.localtime(ahora):%Y-%m-%d %H:%M} · {tickets.count()} tickets revisados · "
                          f"{avisos} avisos nuevos")
