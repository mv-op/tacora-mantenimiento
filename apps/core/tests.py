from django.conf import settings
from django.test import Client, TestCase

from apps.usuarios.models import AceptacionTerminos, Rol, Usuario


class FalloCsrfTests(TestCase):
    def setUp(self):
        self.cliente = Client(enforce_csrf_checks=True)
        u = Usuario.objects.create_user("op", password="x", rol=Rol.OPERADOR, debe_cambiar_clave=False)
        AceptacionTerminos.objects.create(usuario=u, version=settings.TERMINOS_VERSION)
        self.cliente.force_login(u)

    def test_pagina_clara(self):
        r = self.cliente.post("/salir/", {"csrfmiddlewaretoken": "viejo"})
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "Página desactualizada", status_code=403)
        self.assertNotContains(r, "Solicitud abortada", status_code=403)

    def test_htmx_recarga_la_pagina(self):
        r = self.cliente.post("/salir/", HTTP_HX_REQUEST="true")
        self.assertEqual((r.status_code, r["HX-Refresh"]), (403, "true"))


class MenuTests(TestCase):
    def entrar(self, rol):
        u = Usuario.objects.create_user(f"u_{rol}", password="x", rol=rol, debe_cambiar_clave=False)
        AceptacionTerminos.objects.create(usuario=u, version=settings.TERMINOS_VERSION)
        self.client.force_login(u)

    def test_cada_rol_llega_a_su_pantalla_principal(self):
        for rol, destino in [(Rol.OPERADOR, "/reportar/"), (Rol.TECNICO, "/ordenes/"),
                             (Rol.COORDINADOR, "/bandeja/"), (Rol.ADMIN, "/cuenta/")]:
            self.entrar(rol)
            self.assertRedirects(self.client.get("/"), destino, fetch_redirect_response=False)

    def test_menu_del_coordinador_y_opcion_resaltada(self):
        self.entrar(Rol.COORDINADOR)
        r = self.client.get("/sla/")
        for etiqueta in ("Bandeja", "Máquinas", "Plazos", "Reportar", "Cuenta"):
            self.assertContains(r, f"{etiqueta}\n")
        activas = [opcion.etiqueta for opcion, activa in r.context["menu"] if activa]
        self.assertEqual(activas, ["Plazos"])

    def test_menu_del_operador_no_muestra_bandeja(self):
        self.entrar(Rol.OPERADOR)
        r = self.client.get("/reportes/")
        self.assertEqual([o.etiqueta for o, _ in r.context["menu"]], ["Reportar falla", "Mis reportes", "Cuenta"])
        self.assertEqual([o.etiqueta for o, activa in r.context["menu"] if activa], ["Mis reportes"])

    def test_sin_sesion_no_hay_menu(self):
        self.assertNotContains(self.client.get("/ingresar/"), 'id="menu"')
