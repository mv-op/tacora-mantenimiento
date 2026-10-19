from django.db import IntegrityError
from django.test import TestCase

from .models import Criticidad, ReglaSLA, formato_minutos


class ReglasSLATests(TestCase):
    def test_reglas_iniciales_del_plan(self):
        reglas = {r.criticidad: (r.minutos_para_asignar, r.minutos_para_resolver)
                  for r in ReglaSLA.objects.filter(activa=True)}
        self.assertEqual(reglas, {
            Criticidad.CRITICA: (30, 480),
            Criticidad.URGENTE: (120, 1440),
            Criticidad.IMPORTANTE: (480, 4320),
        })

    def test_quedan_en_el_historial(self):
        regla = ReglaSLA.objects.get(criticidad=Criticidad.CRITICA)
        self.assertEqual(regla.history.first().history_change_reason, "Valores iniciales del plan")

    def test_solo_una_regla_activa_por_criticidad(self):
        with self.assertRaises(IntegrityError):
            ReglaSLA.objects.create(criticidad=Criticidad.CRITICA, minutos_para_asignar=1, minutos_para_resolver=2)

    def test_formato_minutos(self):
        self.assertEqual([formato_minutos(m) for m in (30, 120, 90, 4320)], ["30 min", "2 h", "1 h 30 min", "72 h"])
