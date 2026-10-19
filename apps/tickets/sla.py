"""Semáforo de SLA y tiempo en pausa. Se calcula desde las fechas en cada consulta; nada se guarda.

- Reportado: cuenta el plazo para asignar, desde que se reportó.
- Asignado, en proceso o en pausa: cuenta el plazo para resolver, desde que se reportó.
  La pausa no detiene el reloj; el tiempo en pausa se informa aparte.
- Resuelto: el semáforo queda congelado en el momento en que se resolvió.
- Cerrado o anulado: sin semáforo.

Se usa la regla SLA activa de la criticidad (si el coordinador la cambia, aplica a los abiertos).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from .models import Estado, ReglaSLA, TipoEvento

UMBRAL_AMARILLO = 0.70
UMBRAL_ROJO = 1.00


@dataclass
class Semaforo:
    meta: str            # "asignar" o "resolver"
    inicio: datetime
    limite: datetime
    medido_en: datetime  # ahora, o cuando se resolvió (congelado)
    congelado: bool

    @property
    def fraccion(self):
        total = (self.limite - self.inicio).total_seconds()
        return (self.medido_en - self.inicio).total_seconds() / total if total > 0 else 1.0

    @property
    def color(self):
        if self.fraccion >= UMBRAL_ROJO:
            return "rojo"
        return "amarillo" if self.fraccion >= UMBRAL_AMARILLO else "verde"

    @property
    def restante(self):
        return self.limite - self.medido_en

    @property
    def etiqueta(self):
        return "Asignar antes de" if self.meta == "asignar" else "Resolver antes de"


def reglas_activas():
    """{criticidad: ReglaSLA}. Conviene pedirlas una vez por pantalla y pasarlas a semaforo()."""
    return {r.criticidad: r for r in ReglaSLA.objects.filter(activa=True)}


def semaforo(ticket, reglas=None, ahora=None):
    reglas = reglas if reglas is not None else reglas_activas()
    regla = reglas.get(ticket.criticidad)
    if regla is None or ticket.estado in (Estado.CERRADO, Estado.ANULADO):
        return None
    ahora = ahora or timezone.now()
    if ticket.estado == Estado.REPORTADO:
        meta, minutos = "asignar", regla.minutos_para_asignar
    else:
        meta, minutos = "resolver", regla.minutos_para_resolver
    congelado = ticket.estado == Estado.RESUELTO and ticket.resuelto_en is not None
    return Semaforo(meta=meta, inicio=ticket.reportado_en, limite=ticket.reportado_en + timedelta(minutes=minutos),
                    medido_en=ticket.resuelto_en if congelado else ahora, congelado=congelado)


def tiempo_en_pausa(ticket, ahora=None):
    """Suma de los ratos entre cada pausa y su reanudación (o hasta ahora si sigue en pausa)."""
    ahora = ahora or timezone.now()
    total, desde = timedelta(), None
    for evento in ticket.eventos.filter(tipo__in=[TipoEvento.PAUSAR, TipoEvento.REANUDAR]).order_by("fecha", "pk"):
        if evento.tipo == TipoEvento.PAUSAR:
            desde = evento.fecha
        elif desde:
            total += evento.fecha - desde
            desde = None
    if desde:
        total += ahora - desde
    return total


def duracion(delta):
    """timedelta → '2 h 05 min' (sin signo)."""
    minutos = int(abs(delta.total_seconds()) // 60)
    horas, resto = divmod(minutos, 60)
    if horas >= 24:
        dias, horas = divmod(horas, 24)
        return f"{dias} d {horas} h"
    return f"{horas} h {resto:02d} min" if horas else f"{resto} min"
