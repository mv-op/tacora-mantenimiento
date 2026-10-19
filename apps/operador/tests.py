import threading
import uuid

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase

from apps.activos.models import EstadoCuraduria, Nivel, NodoActivo, Origen
from apps.tickets.models import Estado, EventoTicket, Ticket, TipoEvento
from apps.tickets.servicios import crear_ticket
from apps.usuarios.models import AceptacionTerminos, Rol, Usuario

DESCRIPCION = "La bomba hace un ruido fuerte y gotea aceite."


def operador(username="op"):
    u = Usuario.objects.create_user(username, password="x", rol=Rol.OPERADOR, debe_cambiar_clave=False)
    AceptacionTerminos.objects.create(usuario=u, version=settings.TERMINOS_VERSION)
    return u


class Base(TestCase):
    def setUp(self):
        self.op = operador()
        self.client.force_login(self.op)
        self.maquina = NodoActivo.objects.create(nombre="Laminadora 6", nivel=Nivel.MAQUINA)
        self.unidad = NodoActivo.objects.create(nombre="Corte", nivel=Nivel.UNIDAD, padre=self.maquina)

    def enviar(self, **cambios):
        datos = {"uuid": str(uuid.uuid4()), "nodo": self.unidad.pk, "descripcion": DESCRIPCION, "criticidad": "urgente"}
        datos.update(cambios)
        return self.client.post("/reportes/enviar/", datos), datos


class MosaicoTests(Base):
    def test_maquinas_y_bajar_un_nivel(self):
        NodoActivo.objects.create(nombre="Vieja", nivel=Nivel.MAQUINA, is_active=False)
        r = self.client.get("/reportar/")
        self.assertContains(r, "Laminadora 6")
        self.assertNotContains(r, "Vieja")
        self.assertContains(r, "+ Crear máquina")
        r = self.client.get(f"/reportar/{self.maquina.pk}/")
        self.assertContains(r, "Reportar falla aquí")
        self.assertContains(r, "Paso 2 de 5")
        self.assertContains(r, "bg-emerald-600")  # color de Unidad
        self.assertContains(r, "Corte")
        self.assertContains(r, "+ Crear unidad")

    def test_componente_no_ofrece_crear_hijos(self):
        padre = self.unidad
        for nivel in (Nivel.SISTEMA, Nivel.EQUIPO, Nivel.COMPONENTE):
            padre = NodoActivo.objects.create(nombre=f"N{nivel}", nivel=nivel, padre=padre)
        r = self.client.get(f"/reportar/{padre.pk}/")
        self.assertContains(r, "Reportar falla aquí")
        self.assertContains(r, "Usted está en: Componente")
        self.assertNotContains(r, "+ Crear")

    def test_formulario_de_descripcion(self):
        r = self.client.get(f"/reportar/{self.unidad.pk}/describir/")
        self.assertContains(r, "Laminadora 6 › Corte")
        for etiqueta in ("Crítica", "Urgente", "Importante"):
            self.assertContains(r, etiqueta)
        self.assertNotContains(r, "<select")


class CrearNodoTests(Base):
    def test_crea_pendiente_de_curaduria(self):
        r = self.client.post("/reportar/crear/", {"padre": self.unidad.pk, "nombre": "  Hidráulico  "})
        nodo = NodoActivo.objects.get(nombre="Hidráulico")
        self.assertRedirects(r, f"/reportar/{nodo.pk}/", fetch_redirect_response=False)
        self.assertEqual((nodo.nivel, nodo.padre, nodo.origen, nodo.estado_curaduria, nodo.creado_por),
                         (Nivel.SISTEMA, self.unidad, Origen.OPERADOR, EstadoCuraduria.PENDIENTE, self.op))

    def test_si_ya_existe_usa_el_existente(self):
        self.client.post("/reportar/crear/", {"padre": self.maquina.pk, "nombre": "CORTE"})
        self.assertEqual(NodoActivo.objects.filter(nivel=Nivel.UNIDAD).count(), 1)

    def test_crear_maquina(self):
        self.client.post("/reportar/crear/", {"nombre": "Extrusora 2"})
        self.assertTrue(NodoActivo.objects.filter(nombre="Extrusora 2", nivel=Nivel.MAQUINA, padre=None).exists())

    def test_nombre_vacio(self):
        r = self.client.post("/reportar/crear/", {"padre": self.unidad.pk, "nombre": "---"})
        self.assertContains(r, "letras o números")

    def test_nombres_usados_en_otras_partes(self):
        bobinado = NodoActivo.objects.create(nombre="Bobinado", nivel=Nivel.UNIDAD, padre=self.maquina)
        for unidad in (self.unidad, bobinado):
            NodoActivo.objects.create(nombre="Hidráulico", nivel=Nivel.SISTEMA, padre=unidad)
        NodoActivo.objects.create(nombre="Eléctrico", nivel=Nivel.SISTEMA, padre=bobinado)
        nueva = NodoActivo.objects.create(nombre="Embobinado", nivel=Nivel.UNIDAD, padre=self.maquina)
        # Sin escribir: los más usados de ese nivel, el más común primero.
        r = self.client.get(f"/reportar/crear/?padre={nueva.pk}")
        self.assertEqual([n for n, _ in r.context["usados"]], ["Hidráulico", "Eléctrico"])
        self.assertContains(r, "Nombres usados en otras partes")
        # Escribiendo con error: lo encuentra igual.
        r = self.client.get("/reportar/sugerencias/", {"padre": nueva.pk, "nombre": "hidraulco"})
        self.assertEqual(r.context["usados"][0], ("Hidráulico", 2))
        # Donde ya existe, no lo ofrece como "usado en otras partes" sino como "ya existe aquí".
        r = self.client.get("/reportar/sugerencias/", {"padre": self.unidad.pk, "nombre": "hidraulico"})
        self.assertEqual([n.nombre for n in r.context["sugerencias"]], ["Hidráulico"])
        self.assertNotIn("Hidráulico", [n for n, _ in r.context["usados"]])

    def test_sugerencias_difusas(self):
        NodoActivo.objects.create(nombre="Bobinado", nivel=Nivel.UNIDAD, padre=self.maquina)
        r = self.client.get("/reportar/sugerencias/", {"padre": self.maquina.pk, "nombre": "cortte"})
        self.assertContains(r, "Corte")
        self.assertNotContains(r, "Bobinado")


class EnviarReporteTests(Base):
    def test_crea_ticket_y_evento(self):
        r, datos = self.enviar()
        self.assertEqual(r.status_code, 201)
        ticket = Ticket.objects.get()
        self.assertEqual((ticket.nodo, ticket.estado, ticket.criticidad, ticket.reportado_por, str(ticket.uuid_cliente)),
                         (self.unidad, Estado.REPORTADO, "urgente", self.op, datos["uuid"]))
        evento = EventoTicket.objects.get()
        self.assertEqual((evento.tipo, evento.estado_hacia, evento.actor), (TipoEvento.CREAR, Estado.REPORTADO, self.op))
        self.assertEqual(r.json()["url"], f"/reportes/{ticket.pk}/")

    def test_enviado_dos_veces_crea_un_solo_ticket(self):
        """Condición de cierre de la Fase 4."""
        r1, datos = self.enviar()
        r2 = self.client.post("/reportes/enviar/", datos)
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertEqual(r1.json()["ticket"], r2.json()["ticket"])
        self.assertFalse(r2.json()["creado"])
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(EventoTicket.objects.count(), 1)

    def test_reenvio_tardio_no_vuelve_a_validar(self):
        r, datos = self.enviar()
        self.unidad.is_active = False
        self.unidad.save()
        r2 = self.client.post("/reportes/enviar/", datos)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(Ticket.objects.count(), 1)

    def test_descripcion_se_guarda_sin_modificar(self):
        texto = "  Ruido FUERTE…\n¡desde ayer!  sin cambios  "
        self.enviar(descripcion=texto)
        self.assertEqual(Ticket.objects.get().descripcion, texto)

    def test_validaciones(self):
        for cambios, mensaje in [
            ({"descripcion": "corta"}, "al menos 20"),
            ({"descripcion": " " * 30 + "x"}, "al menos 20"),
            ({"criticidad": "rara"}, "criticidad"),
            ({"nodo": "999"}, "ya no está disponible"),
            ({"nodo": "abc"}, "ya no está disponible"),
            ({"uuid": "no-es-uuid"}, "código válido"),
        ]:
            r, _ = self.enviar(**cambios)
            self.assertEqual(r.status_code, 400, cambios)
            self.assertIn(mensaje, " ".join(r.json()["errores"]))
        self.assertEqual(Ticket.objects.count(), 0)

    def test_sin_sesion_no_responde_json(self):
        self.client.logout()
        r, _ = self.enviar()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Ticket.objects.count(), 0)


class MisReportesTests(Base):
    def test_solo_ve_los_suyos(self):
        otro = operador("otro")
        mio, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.unidad, descripcion=DESCRIPCION,
                              criticidad="critica", reportado_por=self.op)
        ajeno, _ = crear_ticket(uuid_cliente=uuid.uuid4(), nodo=self.maquina, descripcion="Ticket de otra persona aquí",
                                criticidad="importante", reportado_por=otro)
        r = self.client.get("/reportes/")
        self.assertContains(r, f"#{mio.pk}")
        self.assertNotContains(r, f"#{ajeno.pk}")
        self.assertEqual(self.client.get(f"/reportes/{ajeno.pk}/").status_code, 404)
        r = self.client.get(f"/reportes/{mio.pk}/?enviado=1")
        self.assertContains(r, "enviado")
        self.assertContains(r, "Reporte creado")


class EnvioSimultaneoTests(TransactionTestCase):
    """Dos envíos del mismo reporte al mismo tiempo (red lenta + reintento) crean un solo ticket."""

    def test_dos_hilos_mismo_uuid(self):
        op = Usuario.objects.create_user("op", password="x")
        nodo = NodoActivo.objects.create(nombre="M1", nivel=Nivel.MAQUINA)
        codigo = uuid.uuid4()
        resultados = []

        def enviar():
            try:
                resultados.append(crear_ticket(uuid_cliente=codigo, nodo=nodo, descripcion=DESCRIPCION,
                                               criticidad="critica", reportado_por=op))
            finally:
                connection.close()

        hilos = [threading.Thread(target=enviar) for _ in range(2)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(sorted(creado for _, creado in resultados), [False, True])
