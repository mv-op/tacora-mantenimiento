# CMMS Tecnosur Mantenimiento

El plan está en `docs/PLAN.md`.

## Puesta en marcha en local (Windows)

```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # y ajustar SECRET_KEY, DEBUG=True, ALLOWED_HOSTS=localhost,127.0.0.1
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

La base SQLite queda en `../tacora-mantenimiento-data/` (se cambia con `DATA_DIR` en `.env`).

## Tailwind

Se usa el ejecutable standalone de Tailwind v4 (sin Node.js), guardado en `bin/` (no se sube a Git).
El CSS compilado `static/css/app.css` sí se sube, así el servidor no necesita Tailwind.

Descargar el ejecutable (una vez):
https://github.com/tailwindlabs/tailwindcss/releases/download/v4.1.14/tailwindcss-windows-x64.exe → `bin/tailwindcss.exe`

Compilar mientras se editan plantillas:

```powershell
bin\tailwindcss.exe -i static/src/app.css -o static/css/app.css --watch
```

Antes de hacer commit:

```powershell
bin\tailwindcss.exe -i static/src/app.css -o static/css/app.css --minify
```
