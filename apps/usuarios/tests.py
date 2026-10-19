import time
from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import acceso
from .models import AceptacionTerminos, Rol, Usuario

CLAVE_PROPIA = "Laminadora#2026"


def crear_usuario(username="juan", **kw):
    return Usuario.objects.create_user(username, password=settings.CLAVE_INICIAL, nombre_visible="Juan Pérez",
                                       rol=Rol.OPERADOR, **kw)


def listo_para_usar(u):
    """Usuario que ya cambió la contraseña y aceptó los términos."""
    u.set_password(CLAVE_PROPIA)
    u.debe_cambiar_clave = False
    u.save()
    AceptacionTerminos.objects.create(usuario=u, version=settings.TERMINOS_VERSION)
    return u


class IngresoTests(TestCase):
    def test_sin_sesion_va_a_ingresar(self):
        r = self.client.get("/")
        self.assertRedirects(r, "/ingresar/?next=/", fetch_redirect_response=False)

    def test_contrasena_incorrecta(self):
        crear_usuario()
        r = self.client.post("/ingresar/", {"usuario": "juan", "clave": "mala"})
        self.assertContains(r, "Usuario o contraseña incorrectos")
        self.assertEqual(Usuario.objects.get().intentos_fallidos, 1)

    def test_usuario_sin_distinguir_mayusculas(self):
        listo_para_usar(crear_usuario())
        r = self.client.post("/ingresar/", {"usuario": " JUAN ", "clave": CLAVE_PROPIA})
        self.assertRedirects(r, "/", fetch_redirect_response=False)

    def test_bloqueo_tras_cinco_intentos_y_desbloqueo_por_tiempo(self):
        u = crear_usuario()
        for _ in range(4):
            self.client.post("/ingresar/", {"usuario": "juan", "clave": "mala"})
        r = self.client.post("/ingresar/", {"usuario": "juan", "clave": "mala"})
        self.assertContains(r, "bloqueado")
        # Bloqueado: ni con la contraseña correcta entra.
        r = self.client.post("/ingresar/", {"usuario": "juan", "clave": settings.CLAVE_INICIAL})
        self.assertContains(r, "bloqueado")
        # Pasados los 15 minutos, entra y se limpia el bloqueo.
        Usuario.objects.filter(pk=u.pk).update(bloqueado_hasta=timezone.now() - timedelta(seconds=1))
        r = self.client.post("/ingresar/", {"usuario": "juan", "clave": settings.CLAVE_INICIAL})
        self.assertEqual(r.status_code, 302)
        self.assertIsNone(Usuario.objects.get().bloqueado_hasta)

    def test_inactivo_no_entra(self):
        crear_usuario(is_active=False)
        r = self.client.post("/ingresar/", {"usuario": "juan", "clave": settings.CLAVE_INICIAL})
        self.assertContains(r, "incorrectos")

    def test_next_externo_se_ignora(self):
        listo_para_usar(crear_usuario())
        r = self.client.post("/ingresar/?next=https://otro.com/", {"usuario": "juan", "clave": CLAVE_PROPIA})
        self.assertRedirects(r, "/", fetch_redirect_response=False)

    def test_admin_login_usa_el_ingreso_de_la_app(self):
        r = self.client.get("/admin/login/?next=/admin/")
        self.assertRedirects(r, "/ingresar/?next=/admin/", fetch_redirect_response=False)

    def test_salir(self):
        self.client.force_login(listo_para_usar(crear_usuario()))
        self.client.post("/salir/")
        self.assertEqual(self.client.get("/").status_code, 302)


class PrimerIngresoTests(TestCase):
    def setUp(self):
        self.u = crear_usuario()
        self.client.post("/ingresar/", {"usuario": "juan", "clave": settings.CLAVE_INICIAL})

    def test_obliga_cambiar_contrasena(self):
        self.assertRedirects(self.client.get("/"), "/cambiar-clave/", fetch_redirect_response=False)

    def test_no_acepta_la_inicial_ni_solo_numeros_ni_distintas(self):
        for nueva, confirmacion, mensaje in [
            (settings.CLAVE_INICIAL, settings.CLAVE_INICIAL, "contraseña inicial"),
            ("12345678901", "12345678901", "numérica"),
            ("Abcdefgh1", "Abcdefgh2", "no coinciden"),
            ("corta", "corta", "demasiado corta"),
        ]:
            r = self.client.post("/cambiar-clave/", {"nueva": nueva, "confirmacion": confirmacion})
            self.assertContains(r, mensaje)
        self.assertTrue(Usuario.objects.get().debe_cambiar_clave)

    def test_recorrido_completo(self):
        r = self.client.post("/cambiar-clave/", {"nueva": CLAVE_PROPIA, "confirmacion": CLAVE_PROPIA})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        # Sigue con sesión (no lo saca al cambiar la contraseña) y ahora pide términos.
        r = self.client.get("/")
        self.assertRedirects(r, "/terminos/?next=%2F", fetch_redirect_response=False)
        r = self.client.post("/terminos/", {"next": "/"}, HTTP_USER_AGENT="Celular de prueba",
                             HTTP_X_FORWARDED_FOR="190.1.2.3, 10.0.0.1")
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        aceptacion = AceptacionTerminos.objects.get()
        self.assertEqual((aceptacion.version, aceptacion.ip, aceptacion.user_agent),
                         (settings.TERMINOS_VERSION, "190.1.2.3", "Celular de prueba"))
        self.assertContains(self.client.get("/"), "Hola, Juan Pérez")

    def test_version_nueva_de_terminos_obliga_a_aceptar_otra_vez(self):
        listo_para_usar(self.u)
        self.client.force_login(self.u)
        self.assertEqual(self.client.get("/").status_code, 200)
        with override_settings(TERMINOS_VERSION="2"):
            self.assertRedirects(self.client.get("/"), "/terminos/?next=%2F", fetch_redirect_response=False)


class CambioVoluntarioTests(TestCase):
    def test_pide_contrasena_actual(self):
        self.client.force_login(listo_para_usar(crear_usuario()))
        datos = {"nueva": "OtraClave#1", "confirmacion": "OtraClave#1"}
        r = self.client.post("/cambiar-clave/", {"actual": "mala", **datos})
        self.assertContains(r, "actual no es correcta")
        r = self.client.post("/cambiar-clave/", {"actual": CLAVE_PROPIA, **datos})
        self.assertEqual(r.status_code, 302)


class InactividadTests(TestCase):
    def setUp(self):
        self.client.force_login(listo_para_usar(crear_usuario()))
        self.client.get("/")

    def actividad_hace(self, segundos):
        sesion = self.client.session
        sesion[acceso.CLAVE_ACTIVIDAD] = int(time.time()) - segundos
        sesion.save()
        return sesion[acceso.CLAVE_ACTIVIDAD]

    def test_sesion_se_cierra_por_inactividad(self):
        self.actividad_hace(settings.SESION_INACTIVIDAD_MINUTOS * 60 + 1)
        r = self.client.get("/", follow=True)
        self.assertContains(r, "se cerró por inactividad")
        self.assertFalse(r.context["user"].is_authenticated)

    def test_htmx_vencido_redirige_toda_la_pagina(self):
        self.actividad_hace(settings.SESION_INACTIVIDAD_MINUTOS * 60 + 1)
        r = self.client.get("/", HTTP_HX_REQUEST="true")
        self.assertEqual((r.status_code, r["HX-Redirect"]), (204, reverse("ingresar")))

    def test_seguir_conectado_renueva(self):
        self.actividad_hace(60)
        self.assertEqual(self.client.post("/sesion/seguir/").status_code, 204)
        self.assertGreaterEqual(self.client.session[acceso.CLAVE_ACTIVIDAD], int(time.time()) - 1)

    def test_consulta_automatica_no_cuenta_como_uso(self):
        hace_un_minuto = self.actividad_hace(60)
        self.client.get("/", HTTP_X_CONSULTA_AUTOMATICA="1")
        self.assertEqual(self.client.session[acceso.CLAVE_ACTIVIDAD], hace_un_minuto)


class AdminUsuariosTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_superuser("jefe", password="x")
        AceptacionTerminos.objects.create(usuario=self.admin, version=settings.TERMINOS_VERSION)
        self.client.force_login(self.admin)

    def test_superusuario_por_consola(self):
        self.assertEqual((self.admin.rol, self.admin.debe_cambiar_clave), (Rol.ADMIN, False))

    def test_crear_usuario_pone_la_contrasena_inicial(self):
        r = self.client.post("/admin/usuarios/usuario/add/", {
            "username": "maria", "nombre_visible": "María", "first_name": "", "last_name": "", "rol": Rol.TECNICO,
        })
        self.assertEqual(r.status_code, 302)
        maria = Usuario.objects.get(username="maria")
        self.assertTrue(maria.check_password(settings.CLAVE_INICIAL))
        self.assertTrue(maria.debe_cambiar_clave)
        self.assertFalse(maria.is_staff)

    def test_restablecer_contrasena(self):
        u = listo_para_usar(crear_usuario(bloqueado_hasta=timezone.now() + timedelta(minutes=10)))
        self.client.post("/admin/usuarios/usuario/", {"action": "restablecer_clave", "_selected_action": [u.pk]})
        u.refresh_from_db()
        self.assertTrue(u.check_password(settings.CLAVE_INICIAL))
        self.assertTrue(u.debe_cambiar_clave)
        self.assertIsNone(u.bloqueado_hasta)
