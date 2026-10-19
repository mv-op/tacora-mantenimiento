from django.db import migrations


def superusuarios_como_admin(apps, schema_editor):
    Usuario = apps.get_model("usuarios", "Usuario")
    Usuario.objects.filter(is_superuser=True).update(rol="admin", debe_cambiar_clave=False)


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0002_campos_mantenimiento")]

    operations = [migrations.RunPython(superusuarios_como_admin, migrations.RunPython.noop)]
