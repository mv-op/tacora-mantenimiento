from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from apps.usuarios.models import Rol

from .normalizar import normalizar


class Nivel(models.IntegerChoices):
    MAQUINA = 1, "Máquina"
    UNIDAD = 2, "Unidad"
    SISTEMA = 3, "Sistema"
    EQUIPO = 4, "Equipo"
    COMPONENTE = 5, "Componente"


class Origen(models.TextChoices):
    EXCEL = "excel", "Excel"
    OPERADOR = "operador", "Operador"
    ADMIN = "admin", "Administrador"


class EstadoCuraduria(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    APROBADO = "aprobado", "Aprobado"


class NodoActivo(models.Model):
    """Árbol único de activos. Nunca se borra: se desactiva con `is_active=False`."""

    nombre = models.CharField("nombre", max_length=200)
    nombre_normalizado = models.CharField("nombre normalizado", max_length=200, editable=False, db_index=True)
    nivel = models.PositiveSmallIntegerField("nivel", choices=Nivel.choices)
    padre = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="hijos", verbose_name="padre"
    )
    origen = models.CharField("origen", max_length=20, choices=Origen.choices, default=Origen.ADMIN)
    estado_curaduria = models.CharField(
        "estado de curaduría", max_length=20, choices=EstadoCuraduria.choices, default=EstadoCuraduria.APROBADO
    )
    is_active = models.BooleanField("activo", default=True)
    fusionado_en = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="fusionados", verbose_name="fusionado en"
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="nodos_creados", verbose_name="creado por",
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "nodo de activo"
        verbose_name_plural = "nodos de activos"
        ordering = ["nivel", "nombre"]
        constraints = [
            # Sin nombres repetidos entre hermanos activos.
            models.UniqueConstraint(
                fields=["padre", "nombre_normalizado"], condition=Q(is_active=True),
                name="nodo_unico_entre_hermanos",
            ),
            # Las máquinas no tienen padre (NULL no se compara en la regla anterior).
            models.UniqueConstraint(
                fields=["nombre_normalizado"], condition=Q(is_active=True, padre__isnull=True),
                name="maquina_unica",
            ),
        ]

    def __str__(self):
        return self.ruta

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar(self.nombre)
        super().save(*args, **kwargs)

    def clean(self):
        if self.pk and self.padre_id and any(n.pk == self.pk for n in self.padre.ancestros):
            raise ValidationError({"padre": "Un nodo no puede ser su propio padre ni colgar de uno de sus descendientes."})
        if self.pk and self.hijos.exists():
            nivel_guardado = NodoActivo.objects.values_list("nivel", flat=True).get(pk=self.pk)
            if self.nivel != nivel_guardado:
                raise ValidationError({"nivel": "No se puede cambiar el nivel de un nodo que tiene hijos."})
        if self.nivel == Nivel.MAQUINA:
            if self.padre_id:
                raise ValidationError({"padre": "Una máquina no tiene padre."})
        elif not self.padre_id:
            raise ValidationError({"padre": "Este nivel necesita un padre."})
        elif self.padre.nivel != self.nivel - 1:
            raise ValidationError(
                {"padre": f"El padre de un(a) {self.get_nivel_display()} debe ser "
                          f"un(a) {Nivel(self.nivel - 1).label}."}
            )

    @property
    def ancestros(self):
        """Lista desde la máquina hasta este nodo, incluido."""
        cadena, nodo, vistos = [], self, set()
        # Freno de seguridad: el árbol tiene 5 niveles; si hay un ciclo, se corta.
        while nodo and nodo.pk not in vistos and len(cadena) < len(Nivel):
            if nodo.pk:
                vistos.add(nodo.pk)
            cadena.append(nodo)
            nodo = nodo.padre
        return list(reversed(cadena))

    @property
    def maquina(self):
        """La máquina (raíz) a la que pertenece este nodo."""
        return self.ancestros[0]

    @property
    def ruta_padre(self):
        """La ruta sin el propio nombre (para mostrarla pequeña debajo del nombre)."""
        return " › ".join(n.nombre for n in self.ancestros[:-1])

    @property
    def ruta(self):
        return " › ".join(n.nombre for n in self.ancestros)


class CoordinadorMaquina(models.Model):
    coordinador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="maquinas_coordinadas",
        limit_choices_to={"rol": Rol.COORDINADOR}, verbose_name="coordinador",
    )
    maquina = models.ForeignKey(
        NodoActivo, on_delete=models.PROTECT, related_name="coordinadores",
        limit_choices_to={"nivel": Nivel.MAQUINA, "is_active": True}, verbose_name="máquina",
    )

    class Meta:
        verbose_name = "coordinador de máquina"
        verbose_name_plural = "coordinadores de máquinas"
        constraints = [
            models.UniqueConstraint(fields=["coordinador", "maquina"], name="coordinador_maquina_unico"),
        ]

    def __str__(self):
        return f"{self.coordinador} → {self.maquina.nombre}"

    def clean(self):
        if self.maquina_id and self.maquina.nivel != Nivel.MAQUINA:
            raise ValidationError({"maquina": "Solo se pueden asignar máquinas."})
        if self.coordinador_id and self.coordinador.rol != Rol.COORDINADOR:
            raise ValidationError({"coordinador": "El usuario debe tener rol coordinador."})
