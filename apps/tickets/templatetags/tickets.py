from django import template

from ..sla import duracion as _duracion

register = template.Library()


@register.filter
def duracion(delta):
    """{{ algo|duracion }} → '2 h 05 min'."""
    return _duracion(delta) if delta is not None else ""


@register.filter
def epoch_ms(fecha):
    """Fecha → milisegundos desde 1970, para el cronómetro del navegador."""
    return int(fecha.timestamp() * 1000) if fecha else ""
