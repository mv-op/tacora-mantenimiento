import uuid

from django.conf import settings
from django.test import TestCase

from apps.activos.models import CoordinadorMaquina, Nivel, NodoActivo
from apps.tickets.models import CierreTecnico, Estado, EventoTicket, ReglaSLA, Ticket
from apps.tickets.servicios import crear_ticket
from apps.usuarios.models import AceptacionTerminos, Rol, Usuario

CIERRE = {
    "causa_raiz": "Rodamiento desgastado por falta de lubricación.",
    "accion_correctiva": "Se cambió el rodamiento y se lubricó el eje.",
    "repuestos": "",
    "recomendacion_preventiva": "Lubricar cada 15 días según el plan.",
}


def usuario(username, rol):
    u = Usuario.objects.create_user(username, password="x", rol=rol, debe_cambiar_clave=False, nombre_visible=username.title())
    AceptacionTerminos.objects.create(usuario=u, version=settings.TERMINOS_VERSION)
    return u


class PantallasTests(TestCase):
    """El ciclo completo recorrido por las pantallas, como lo harían el coordinador y el técnico."""

    def setUp(self):
        self.operador = usuario("operario", Rol.OPERADOR)
        self.coord = usuario("coordinadora", Rol.COORDINADOR)
        self.tecnico = usuario("tecnico", Rol.TECNICO)
        maquina = NodoActivo.objects.create(nombre="Laminadora 6", nivel=Nivel.MAQUINA)
        unidad = NodoActivo.objects.create(nombre="Corte", nivel=Nivel.UNIDAD, padre=maquina)
        self.otra_maquina = NodoActivo.objects.create(nombre="Extrusora", nivel=Nivel.MAQUINA)
        CoordinadorMaquina.objects.create(coordinador=self.coord, maquina=maquina)
        self.ticket, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=unidad, criticidad="critica",
                                      descripcion="La cuchilla no corta parejo.", reportado_por=self.operador)
        self.ajeno, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.otra_maquina, criticidad="urgente",
                                     descripcion="Ruido raro en la extrusora.", reportado_por=self.operador)
        self.pk = self.ticket.pk

    def como(self, u):
        self.client.force_login(u)

    def estado(self):
        return Ticket.objects.get(pk=self.pk).estado

    def test_recorrido_completo_con_rechazo(self):
        # Coordinador: ve su reporte (no el de otra máquina) y asigna.
        self.como(self.coord)
        r = self.client.get("/bandeja/")
        self.assertContains(r, "Por asignar")
        self.assertContains(r, "La cuchilla no corta parejo.")
        self.assertNotContains(r, "Ruido raro en la extrusora.")
        r = self.client.get(f"/bandeja/{self.pk}/")
        self.assertContains(r, "Asignar técnico")
        self.assertContains(r, "0 tareas activas")
        self.client.post(f"/bandeja/{self.pk}/asignar/", {"tecnico": self.tecnico.pk})
        self.assertEqual(self.estado(), Estado.ASIGNADO)

        # Técnico: lo ve en Mis órdenes, inicia y pausa.
        self.como(self.tecnico)
        r = self.client.get("/ordenes/")
        self.assertContains(r, f"#{self.pk}")
        self.assertContains(r, "Plazo para resolver")
        self.assertContains(self.client.get(f"/ordenes/{self.pk}/"), "Iniciar trabajo")
        self.client.post(f"/ordenes/{self.pk}/iniciar/")
        self.client.post(f"/ordenes/{self.pk}/pausar/", {"motivo": "Falta el repuesto en bodega."})
        self.assertEqual(self.estado(), Estado.EN_PAUSA)

        # Coordinador: responde el contra-reporte.
        self.como(self.coord)
        self.assertContains(self.client.get("/bandeja/"), "Contra-reportes")
        self.assertContains(self.client.get(f"/bandeja/{self.pk}/"), "Falta el repuesto en bodega.")
        self.client.post(f"/bandeja/{self.pk}/responder/", {"comentario": "Ya llegó, continúe por favor."})
        self.assertEqual(self.estado(), Estado.EN_PROCESO)

        # Técnico: finaliza; un cierre corto se rechaza sin perder lo escrito.
        self.como(self.tecnico)
        r = self.client.post(f"/ordenes/{self.pk}/finalizar/", {**CIERRE, "causa_raiz": "corta"})
        self.assertContains(r, "causa raíz con al menos 20")
        self.assertContains(r, CIERRE["accion_correctiva"])
        self.client.post(f"/ordenes/{self.pk}/finalizar/", CIERRE)
        self.assertEqual(self.estado(), Estado.RESUELTO)

        # Coordinador: rechaza con motivo.
        self.como(self.coord)
        self.assertContains(self.client.get(f"/bandeja/{self.pk}/"), "Validar y cerrar")
        self.client.post(f"/bandeja/{self.pk}/rechazar/", {"comentario": "Sigue cortando disparejo."})
        self.assertEqual(self.estado(), Estado.EN_PROCESO)

        # Técnico: ve el motivo y escribe un cierre nuevo.
        self.como(self.tecnico)
        self.assertContains(self.client.get(f"/ordenes/{self.pk}/"), "Sigue cortando disparejo.")
        self.client.post(f"/ordenes/{self.pk}/finalizar/", {**CIERRE, "causa_raiz": "Además la cuchilla estaba desafilada."})

        # Coordinador: valida.
        self.como(self.coord)
        self.client.post(f"/bandeja/{self.pk}/validar/")
        self.assertEqual(self.estado(), Estado.CERRADO)
        self.assertEqual(CierreTecnico.objects.filter(ticket_id=self.pk).count(), 2)
        tipos = list(EventoTicket.objects.filter(ticket_id=self.pk).values_list("tipo", flat=True))
        self.assertEqual(tipos, ["crear", "asignar", "iniciar", "pausar", "reanudar", "resolver", "rechazar", "resolver", "validar"])

        # El operador ve todo el historial en su reporte.
        self.como(self.operador)
        r = self.client.get(f"/reportes/{self.pk}/")
        self.assertContains(r, "Validado y cerrado")

    def test_anular_y_reasignar(self):
        self.como(self.coord)
        otro = usuario("otro_tecnico", Rol.TECNICO)
        self.client.post(f"/bandeja/{self.pk}/asignar/", {"tecnico": self.tecnico.pk, "tipo": "asignar"})
        self.client.post(f"/bandeja/{self.pk}/asignar/", {"tecnico": otro.pk, "tipo": "reasignar"})
        self.assertEqual(Ticket.objects.get(pk=self.pk).tecnico, otro)
        self.assertTrue(EventoTicket.objects.filter(ticket_id=self.pk, tipo="reasignar").exists())
        # Anular solo desde Reportado.
        r = self.client.post(f"/bandeja/{self.pk}/anular/", {"comentario": "Duplicado del reporte anterior."}, follow=True)
        self.assertContains(r, "no permite")

    def test_permisos(self):
        self.como(self.coord)
        self.assertEqual(self.client.get(f"/bandeja/{self.ajeno.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/ordenes/").status_code, 403)
        self.como(self.tecnico)
        self.assertEqual(self.client.get("/bandeja/").status_code, 403)
        self.assertEqual(self.client.get(f"/ordenes/{self.pk}/").status_code, 404)  # aún no es suyo
        self.como(self.operador)
        self.assertEqual(self.client.get("/bandeja/").status_code, 403)
        self.assertEqual(self.client.post(f"/bandeja/{self.pk}/validar/").status_code, 403)

    def test_coordinador_sin_maquinas(self):
        self.como(usuario("nuevo_coord", Rol.COORDINADOR))
        self.assertContains(self.client.get("/bandeja/"), "Aún no tiene máquinas asignadas")

    def test_orden_por_criticidad(self):
        CoordinadorMaquina.objects.create(coordinador=self.coord, maquina=self.otra_maquina)
        self.como(self.coord)
        r = self.client.get("/bandeja/")
        por_asignar = r.context["secciones"][0]["tickets"]
        self.assertEqual([t.criticidad for t in por_asignar], ["critica", "urgente"])


class AjustesTests(TestCase):
    def setUp(self):
        self.coord = usuario("coordinadora", Rol.COORDINADOR)
        self.client.force_login(self.coord)

    def test_ajustar_sla_queda_en_historial(self):
        r = self.client.get("/sla/")
        self.assertContains(r, "Plazo para asignar")
        r = self.client.post("/sla/", {"criticidad": "critica", "asignar_horas": "0", "asignar_min": "45",
                                       "resolver_horas": "10", "resolver_min": "0"}, follow=True)
        self.assertContains(r, "Plazos actualizados")
        regla = ReglaSLA.objects.get(criticidad="critica", activa=True)
        self.assertEqual((regla.minutos_para_asignar, regla.minutos_para_resolver, regla.modificada_por),
                         (45, 600, self.coord))
        self.assertEqual(regla.history.first().history_user, self.coord)

    def test_sla_invalido(self):
        for datos, mensaje in [
            ({"asignar_horas": "9", "asignar_min": "0", "resolver_horas": "8", "resolver_min": "0"}, "menor que"),
            ({"asignar_horas": "0", "asignar_min": "0", "resolver_horas": "8", "resolver_min": "0"}, "mayores que cero"),
            ({"asignar_horas": "x", "asignar_min": "0", "resolver_horas": "8", "resolver_min": "0"}, "números enteros"),
        ]:
            r = self.client.post("/sla/", {"criticidad": "critica", **datos}, follow=True)
            self.assertContains(r, mensaje)

    def test_historial_por_maquina(self):
        operador = usuario("operario", Rol.OPERADOR)
        maquina = NodoActivo.objects.create(nombre="Laminadora 6", nivel=Nivel.MAQUINA)
        ajena = NodoActivo.objects.create(nombre="Extrusora", nivel=Nivel.MAQUINA)
        CoordinadorMaquina.objects.create(coordinador=self.coord, maquina=maquina)
        crear_ticket(uuid_cliente=uuid.uuid4(), nodo=maquina, criticidad="urgente",
                     descripcion="Ruido en el motor principal.", reportado_por=operador)
        r = self.client.get("/maquinas/")
        self.assertContains(r, "Laminadora 6")
        self.assertContains(r, "1 reporte ")
        self.assertNotContains(r, "Extrusora")
        self.assertContains(self.client.get(f"/maquinas/{maquina.pk}/"), "Ruido en el motor principal.")
        self.assertEqual(self.client.get(f"/maquinas/{ajena.pk}/").status_code, 404)


class VariosCoordinadoresTests(TestCase):
    """Una máquina con coordinador de producción y de mantenimiento: ambos ven el reporte."""

    def setUp(self):
        self.produccion = usuario("produccion", Rol.COORDINADOR)
        self.mantenimiento = usuario("mantenimiento", Rol.COORDINADOR)
        self.tecnico = usuario("tecnico", Rol.TECNICO)
        operador = usuario("operario", Rol.OPERADOR)
        self.maquinas = [NodoActivo.objects.create(nombre=f"Máquina {i}", nivel=Nivel.MAQUINA) for i in range(3)]
        CoordinadorMaquina.objects.create(coordinador=self.produccion, maquina=self.maquinas[0])
        for maquina in self.maquinas:
            CoordinadorMaquina.objects.create(coordinador=self.mantenimiento, maquina=maquina)
        self.ticket, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.maquinas[0], criticidad="urgente",
                                      descripcion="Fuga de aceite en la máquina 0.", reportado_por=operador)
        self.otro, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.maquinas[2], criticidad="urgente",
                                    descripcion="Ruido en la máquina 2.", reportado_por=operador)

    def test_ambos_lo_ven_y_solo_uno_asigna(self):
        self.client.force_login(self.produccion)
        r = self.client.get("/bandeja/")
        self.assertContains(r, "Fuga de aceite en la máquina 0.")
        self.assertNotContains(r, "Ruido en la máquina 2.")

        self.client.force_login(self.mantenimiento)
        r = self.client.get("/bandeja/")
        self.assertContains(r, "Fuga de aceite en la máquina 0.")
        self.assertContains(r, "Ruido en la máquina 2.")
        r = self.client.post(f"/bandeja/{self.ticket.pk}/asignar/", {"tecnico": self.tecnico.pk, "tipo": "asignar"},
                             follow=True)
        self.assertContains(r, "Listo: asignado")

        # Producción llega tarde con la página vieja y elige a otro técnico: no reasigna sin querer.
        otro_tecnico = usuario("otro_tecnico", Rol.TECNICO)
        self.client.force_login(self.produccion)
        r = self.client.post(f"/bandeja/{self.ticket.pk}/asignar/", {"tecnico": otro_tecnico.pk, "tipo": "asignar"},
                             follow=True)
        self.assertContains(r, "no permite esta acción")
        self.assertEqual(Ticket.objects.get(pk=self.ticket.pk).tecnico, self.tecnico)
        self.assertEqual(EventoTicket.objects.filter(ticket=self.ticket, tipo__in=["asignar", "reasignar"]).count(), 1)


class AdminMaquinasTests(TestCase):
    def setUp(self):
        admin = Usuario.objects.create_superuser("jefe", password="x")
        AceptacionTerminos.objects.create(usuario=admin, version=settings.TERMINOS_VERSION)
        self.client.force_login(admin)
        self.maquinas = [NodoActivo.objects.create(nombre=f"Máquina {i}", nivel=Nivel.MAQUINA) for i in range(4)]
        self.coord = usuario("mantenimiento", Rol.COORDINADOR)

    def guardar(self, usuario, maquinas, rol=Rol.COORDINADOR):
        return self.client.post(f"/admin/usuarios/usuario/{usuario.pk}/change/", {
            "username": usuario.username, "nombre_visible": "Mantenimiento", "first_name": "", "last_name": "",
            "email": "", "rol": rol, "is_active": "on", "intentos_fallidos": 0,
            "maquinas": [m.pk for m in maquinas],
        })

    def test_asignar_y_quitar_varias_maquinas_desde_la_ficha(self):
        r = self.guardar(self.coord, self.maquinas[:3])
        self.assertEqual(r.status_code, 302)
        self.assertEqual(set(CoordinadorMaquina.objects.filter(coordinador=self.coord).values_list("maquina", flat=True)),
                         {m.pk for m in self.maquinas[:3]})
        self.guardar(self.coord, self.maquinas[2:])
        self.assertEqual(set(CoordinadorMaquina.objects.filter(coordinador=self.coord).values_list("maquina", flat=True)),
                         {m.pk for m in self.maquinas[2:]})
        r = self.client.get(f"/admin/usuarios/usuario/{self.coord.pk}/change/")
        self.assertContains(r, "Máquinas que coordina")

    def test_solo_coordinadores_tienen_maquinas(self):
        tecnico = usuario("tecnico", Rol.TECNICO)
        r = self.guardar(tecnico, self.maquinas[:1], rol=Rol.TECNICO)
        self.assertContains(r, "Solo los usuarios con rol coordinador")
        self.assertFalse(CoordinadorMaquina.objects.filter(coordinador=tecnico).exists())

    def test_crear_coordinador_con_maquinas(self):
        self.client.post("/admin/usuarios/usuario/add/", {
            "username": "nuevo", "nombre_visible": "Nuevo", "first_name": "", "last_name": "",
            "rol": Rol.COORDINADOR, "maquinas": [self.maquinas[0].pk, self.maquinas[1].pk],
        })
        nuevo = Usuario.objects.get(username="nuevo")
        self.assertEqual(CoordinadorMaquina.objects.filter(coordinador=nuevo).count(), 2)

    def test_arbol_avisa_maquinas_sin_coordinador(self):
        CoordinadorMaquina.objects.create(coordinador=self.coord, maquina=self.maquinas[0])
        r = self.client.get("/admin/activos/nodoactivo/arbol/")
        self.assertContains(r, "Máquinas sin coordinador (3)")
