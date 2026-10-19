"""Configuración del CMMS Tecnosur Mantenimiento.

Todos los valores que cambian entre local y servidor se leen desde `.env`.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATA_DIR=(str, str(BASE_DIR.parent / "tacora-mantenimiento-data")),
    SESION_INACTIVIDAD_MINUTOS=(int, 15),
    TERMINOS_VERSION=(str, "1"),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# Carpeta de datos fuera del código: base SQLite (y luego respaldos).
DATA_DIR = Path(env("DATA_DIR"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


# Aplicaciones

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "simple_history",
    "apps.usuarios",
    "apps.core",
    "apps.activos",
    "apps.tickets",
    "apps.notificaciones",
    "apps.agente",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.usuarios.middleware.AccesoMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.usuarios.context_processors.sesion",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Base de datos: SQLite en modo WAL, fuera del código.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "mantenimiento.sqlite3",
        "OPTIONS": {
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA busy_timeout=5000;"
            ),
            "transaction_mode": "IMMEDIATE",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Usuarios

AUTH_USER_MODEL = "usuarios.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "apps.usuarios.validadores.DistintaDeLaInicial"},
]

LOGIN_URL = "ingresar"
LOGIN_REDIRECT_URL = "inicio"

# Contraseña inicial común: se asigna al crear o restablecer un usuario y se cambia en el primer ingreso.
CLAVE_INICIAL = env("CLAVE_INICIAL")

# Bloqueo tras intentos fallidos.
INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15


# Sesión: se cierra al cerrar el navegador y tras un tiempo sin uso.

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESION_INACTIVIDAD_MINUTOS = env("SESION_INACTIVIDAD_MINUTOS")


# Términos de uso: al subir la versión, todos deben aceptar de nuevo.

TERMINOS_VERSION = env("TERMINOS_VERSION")


# Idioma y zona horaria: todo en hora Bogotá.

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True


# Archivos estáticos

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# Seguridad en producción

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
