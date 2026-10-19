"""Menú de navegación por rol. La primera opción es la pantalla principal del rol (a donde llega al entrar)."""

from dataclasses import dataclass

from apps.usuarios.models import Rol


@dataclass(frozen=True)
class Opcion:
    etiqueta: str
    url: str                   # nombre de la URL
    pantallas: frozenset       # nombres de URL donde esta opción queda resaltada


REPORTAR = Opcion("Reportar falla", "reportar", frozenset({"reportar", "reportar_nodo", "crear_nodo", "describir"}))
MIS_REPORTES = Opcion("Mis reportes", "mis_reportes", frozenset({"mis_reportes", "mi_reporte"}))
CUENTA = Opcion("Cuenta", "cuenta", frozenset({"cuenta", "cambiar_clave", "terminos"}))

MENUS = {
    Rol.OPERADOR: [REPORTAR, MIS_REPORTES, CUENTA],
    Rol.TECNICO: [
        Opcion("Mis órdenes", "mis_ordenes", frozenset({"mis_ordenes", "orden", "orden_pausar", "orden_finalizar"})),
        REPORTAR, MIS_REPORTES, CUENTA,
    ],
    Rol.COORDINADOR: [
        Opcion("Bandeja", "bandeja", frozenset({"bandeja", "bandeja_ticket"})),
        Opcion("Máquinas", "maquinas", frozenset({"maquinas", "historial_maquina"})),
        Opcion("SLA", "ajustar_sla", frozenset({"ajustar_sla"})),
        Opcion("Reportar", "reportar", REPORTAR.pantallas),
        CUENTA,
    ],
    Rol.ADMIN: [CUENTA, Opcion("Admin", "admin:index", frozenset()), REPORTAR],
}


def menu_de(usuario):
    return MENUS.get(usuario.rol, [CUENTA])


def pantalla_principal(usuario):
    return menu_de(usuario)[0].url
