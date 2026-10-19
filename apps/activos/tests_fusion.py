import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.tickets.servicios import crear_ticket
from apps.usuarios.models import AceptacionTerminos, Rol, Usuario

from .models import CoordinadorMaquina, Nivel, NodoActivo
from .servicios import fusionar


def nodo(nombre, padre=None):
    return NodoActivo.objects.create(nombre=nombre, nivel=padre.nivel + 1 if padre else Nivel.MAQUINA, padre=padre)


class FusionTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user("op")
        self.maquina = nodo("Laminadora 6")
        self.corte = nodo("Corte", self.maquina)
        self.bueno = nodo("Hidráulico", self.corte)
        self.malo = nodo("Hidraulicoo", self.corte)

    def ticket(self, en):
        return crear_ticket(uuid_cliente=uuid.uuid4(), nodo=en, descripcion="Falla de prueba con texto largo",
                            criticidad="urgente", reportado_por=self.usuario)[0]

    def test_mueve_tickets_e_hijos_y_desactiva(self):
        t = self.ticket(self.malo)
        bomba = nodo("Bomba", self.malo)
        resumen = fusionar(self.bueno, self.malo)
        t.refresh_from_db(); bomba.refresh_from_db(); self.malo.refresh_from_db()
        self.assertEqual(t.nodo, self.bueno)
        self.assertEqual(bomba.padre, self.bueno)
        self.assertEqual((self.malo.is_active, self.malo.fusionado_en), (False, self.bueno))
        self.assertEqual(resumen, {"tickets": 1, "hijos_movidos": 1, "hijos_fusionados": 0})
        self.assertIn("Fusión", self.malo.history.first().history_change_reason)
        self.assertIn("Fusión", t.history.first().history_change_reason)

    def test_hijos_con_el_mismo_nombre_se_fusionan(self):
        bomba_buena = nodo("Bomba", self.bueno)
        bomba_mala = nodo("BOMBA", self.malo)
        sello = nodo("Sello", bomba_mala)
        t = self.ticket(bomba_mala)
        resumen = fusionar(self.bueno, self.malo)
        sello.refresh_from_db(); t.refresh_from_db(); bomba_mala.refresh_from_db()
        self.assertEqual(sello.padre, bomba_buena)
        self.assertEqual(t.nodo, bomba_buena)
        self.assertEqual(bomba_mala.fusionado_en, bomba_buena)
        self.assertEqual(resumen["hijos_fusionados"], 1)
        self.assertEqual(self.bueno.hijos.filter(is_active=True).count(), 1)

    def test_maquinas_mueven_coordinadores_sin_duplicar(self):
        coord = Usuario.objects.create_user("coord", rol=Rol.COORDINADOR)
        otra = nodo("Laminadora Seis")
        CoordinadorMaquina.objects.create(coordinador=coord, maquina=self.maquina)
        CoordinadorMaquina.objects.create(coordinador=coord, maquina=otra)
        fusionar(self.maquina, otra)
        self.assertEqual(list(CoordinadorMaquina.objects.values_list("maquina", flat=True)), [self.maquina.pk])

    def test_validaciones(self):
        for correcto, duplicado in [(self.bueno, self.bueno), (self.corte, self.bueno)]:
            with self.assertRaises(ValidationError):
                fusionar(correcto, duplicado)


class AdminFusionTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_superuser("jefe", password="x")
        AceptacionTerminos.objects.create(usuario=self.admin, version=settings.TERMINOS_VERSION)
        self.client.force_login(self.admin)
        self.maquina = nodo("Laminadora 6")
        self.bueno = nodo("Corte", self.maquina)
        self.malo = nodo("Corte 2", self.maquina)

    def accion(self, **extra):
        datos = {"action": "fusionar_nodos", "_selected_action": [self.bueno.pk, self.malo.pk], **extra}
        return self.client.post("/admin/activos/nodoactivo/", datos, follow=True)

    def test_paso_1_muestra_tarjetas_y_no_fusiona(self):
        r = self.accion()
        self.assertContains(r, "Toque el nodo")
        self.assertContains(r, "Corte 2")
        self.assertTrue(NodoActivo.objects.get(pk=self.malo.pk).is_active)

    def test_paso_2_fusiona(self):
        r = self.accion(correcto=self.bueno.pk)
        self.assertContains(r, "Fusionados en")
        self.malo.refresh_from_db()
        self.assertEqual(self.malo.fusionado_en, self.bueno)

    def test_distinto_nivel(self):
        unidad = self.bueno
        sistema = nodo("Hidráulico", unidad)
        r = self.client.post("/admin/activos/nodoactivo/",
                             {"action": "fusionar_nodos", "_selected_action": [unidad.pk, sistema.pk]}, follow=True)
        self.assertContains(r, "mismo nivel")
