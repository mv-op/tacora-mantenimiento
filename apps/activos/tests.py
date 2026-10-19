from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from .models import Nivel, NodoActivo
from .normalizar import normalizar


class NormalizarTests(TestCase):
    def test_quita_tildes_signos_y_mayusculas(self):
        self.assertEqual(normalizar("  Bomba Nº 2-A (Hidráulica) "), "bomba no 2 a hidraulica")


class NodoActivoTests(TestCase):
    def setUp(self):
        self.maquina = NodoActivo.objects.create(nombre="Extrusora 1", nivel=Nivel.MAQUINA)

    def test_guarda_nombre_normalizado(self):
        self.assertEqual(self.maquina.nombre_normalizado, "extrusora 1")

    def test_nivel_del_padre_debe_ser_el_anterior(self):
        nodo = NodoActivo(nombre="Motor", nivel=Nivel.SISTEMA, padre=self.maquina)
        with self.assertRaises(ValidationError):
            nodo.full_clean()

    def test_maquina_sin_padre(self):
        with self.assertRaises(ValidationError):
            NodoActivo(nombre="Unidad", nivel=Nivel.UNIDAD).full_clean()

    def test_no_repite_nombre_entre_hermanos_activos(self):
        NodoActivo.objects.create(nombre="Unidad Térmica", nivel=Nivel.UNIDAD, padre=self.maquina)
        with self.assertRaises(IntegrityError):
            NodoActivo.objects.create(nombre="unidad termica", nivel=Nivel.UNIDAD, padre=self.maquina)

    def test_no_repite_maquina(self):
        with self.assertRaises(IntegrityError):
            NodoActivo.objects.create(nombre="EXTRUSORA 1", nivel=Nivel.MAQUINA)

    def test_inactivo_libera_el_nombre(self):
        self.maquina.is_active = False
        self.maquina.save()
        NodoActivo.objects.create(nombre="Extrusora 1", nivel=Nivel.MAQUINA)

    def test_ruta_y_historial(self):
        unidad = NodoActivo.objects.create(nombre="Unidad A", nivel=Nivel.UNIDAD, padre=self.maquina)
        self.assertEqual(unidad.ruta, "Extrusora 1 › Unidad A")
        unidad.nombre = "Unidad B"
        unidad.save()
        self.assertEqual(unidad.history.count(), 2)


class CiclosTests(TestCase):
    def setUp(self):
        self.maquina = NodoActivo.objects.create(nombre="Laminadora 6", nivel=Nivel.MAQUINA)

    def test_no_puede_ser_su_propio_padre(self):
        # Caso real: editar la máquina, pasarla a Unidad y ponerla como su propio padre.
        self.maquina.nivel = Nivel.UNIDAD
        self.maquina.padre = NodoActivo.objects.get(pk=self.maquina.pk)
        with self.assertRaises(ValidationError):
            self.maquina.full_clean()

    def test_no_cambia_nivel_con_hijos(self):
        NodoActivo.objects.create(nombre="Corte", nivel=Nivel.UNIDAD, padre=self.maquina)
        self.maquina.nivel = Nivel.UNIDAD
        with self.assertRaises(ValidationError):
            self.maquina.full_clean()

    def test_ruta_no_se_cuelga_con_un_ciclo(self):
        NodoActivo.objects.filter(pk=self.maquina.pk).update(padre=self.maquina, nivel=Nivel.UNIDAD)
        nodo = NodoActivo.objects.get(pk=self.maquina.pk)
        self.assertEqual(nodo.ruta, "Laminadora 6")
