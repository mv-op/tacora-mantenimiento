from django.db import migrations
from django.utils import timezone

# Punto de partida del plan, en minutos. El coordinador las ajusta después.
REGLAS_INICIALES = [
    ("critica", 30, 8 * 60),
    ("urgente", 2 * 60, 24 * 60),
    ("importante", 8 * 60, 72 * 60),
]


def crear_reglas(apps, schema_editor):
    ReglaSLA = apps.get_model("tickets", "ReglaSLA")
    HistoricalReglaSLA = apps.get_model("tickets", "HistoricalReglaSLA")
    for criticidad, asignar, resolver in REGLAS_INICIALES:
        if ReglaSLA.objects.filter(criticidad=criticidad, activa=True).exists():
            continue
        regla = ReglaSLA.objects.create(
            criticidad=criticidad, minutos_para_asignar=asignar, minutos_para_resolver=resolver, activa=True
        )
        HistoricalReglaSLA.objects.create(
            id=regla.id, criticidad=criticidad, minutos_para_asignar=asignar, minutos_para_resolver=resolver,
            activa=True, modificada_en=regla.modificada_en, history_date=timezone.now(), history_type="+",
            history_change_reason="Valores iniciales del plan",
        )


class Migration(migrations.Migration):
    dependencies = [("tickets", "0001_initial")]

    operations = [migrations.RunPython(crear_reglas, migrations.RunPython.noop)]
