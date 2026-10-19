"""Color y texto de cada nivel del árbol, para que se vea en qué nivel está el operador.

Las clases van completas aquí para que Tailwind las encuentre. No se usan rojo, naranja ni amarillo:
son los colores de la criticidad.
"""

from django import template

register = template.Library()

ESTILOS = {
    1: {"articulo": "la", "banda": "bg-blue-600 text-white", "chip": "bg-blue-600 text-white",
        "boton": "border-l-8 border-blue-500 bg-blue-50 text-blue-950", "suave": "bg-blue-100 text-blue-900"},
    2: {"articulo": "la", "banda": "bg-emerald-600 text-white", "chip": "bg-emerald-600 text-white",
        "boton": "border-l-8 border-emerald-500 bg-emerald-50 text-emerald-950", "suave": "bg-emerald-100 text-emerald-900"},
    3: {"articulo": "el", "banda": "bg-violet-600 text-white", "chip": "bg-violet-600 text-white",
        "boton": "border-l-8 border-violet-500 bg-violet-50 text-violet-950", "suave": "bg-violet-100 text-violet-900"},
    4: {"articulo": "el", "banda": "bg-cyan-600 text-white", "chip": "bg-cyan-600 text-white",
        "boton": "border-l-8 border-cyan-500 bg-cyan-50 text-cyan-950", "suave": "bg-cyan-100 text-cyan-900"},
    5: {"articulo": "el", "banda": "bg-fuchsia-600 text-white", "chip": "bg-fuchsia-600 text-white",
        "boton": "border-l-8 border-fuchsia-500 bg-fuchsia-50 text-fuchsia-950", "suave": "bg-fuchsia-100 text-fuchsia-900"},
}


@register.filter
def estilo_nivel(nivel, clave):
    """Uso: {{ nodo.nivel|estilo_nivel:"boton" }}"""
    try:
        return ESTILOS[int(nivel)][clave]
    except (KeyError, TypeError, ValueError):
        return ""
