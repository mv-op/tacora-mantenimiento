# Progreso del proyecto — CMMS Tecnosur Mantenimiento

Última actualización: 19 de octubre de 2026.
Siguiente sesión: **Fase 7 — Despliegue piloto**.

---

## 1. Estado general

| Fase | Estado | Commit |
| --- | --- | --- |
| 1. Base del proyecto | ✅ Lista | `bbb7efd` |
| 2. Modelo de datos y admin | ✅ Lista (falta cargar el Excel real) | `1d0615c`, `db303f1`, `ec09466` |
| 3. Acceso y cumplimiento | ✅ Lista | `0126ae7` |
| 4. Pantalla del operador | ✅ Lista | `15522a8` |
| 5. Coordinador y técnico | ✅ Lista | `3fb42e8` |
| 6. Notificaciones | ✅ Lista | `d3aa606` |
| 7. Despliegue piloto | ⏳ **Siguiente** | — |
| 8. Dashboards | Pendiente | — |
| 9. Agente de monitoreo | Pendiente | — |

- 132 pruebas automáticas, todas pasan: `.venv\Scripts\python manage.py test apps`
- Repositorio Git local en la rama `main`. **Aún no se ha subido a GitHub.**

---

## 2. Decisiones que cambiaron respecto al plan original

Ya están reflejadas en `docs/PLAN.md` y `CLAUDE.md` cuando aplica.

1. **Acceso sin PIN.** Usuario + contraseña. Contraseña inicial común (`CLAVE_INICIAL` en `.env`, hoy `tq1234567` en local) que cada persona cambia en su primer ingreso: mínimo 8 caracteres, no solo números, distinta de la inicial. El admin crea usuarios sin escribir contraseña y puede "Restablecer contraseña inicial" y "Desbloquear".
2. **Bloqueo:** 5 intentos fallidos → 15 minutos.
3. **Inactividad:** 15 min (`SESION_INACTIVIDAD_MINUTOS` en `.env`), con aviso "Seguir conectado" un minuto antes. La sesión también se cierra al cerrar el navegador.
4. **Términos:** texto genérico en plantilla; versión en `.env` (`TERMINOS_VERSION`). Al subirla, todos aceptan de nuevo.
5. **SLA guardado en minutos.** En la interfaz se llama **"Plazos"**. El reloj **no se detiene en pausa**; el tiempo en pausa se muestra aparte.
6. **Reportar en cualquier nivel** del árbol, no solo en Componente. Descripción mínima: 20 caracteres.
7. **Cierre técnico:** 3 campos obligatorios (20 caracteres mínimo) + repuestos opcional. Motivos de pausa, rechazo y anulación: 10 caracteres mínimo.
8. **Reasignar técnico** permitido en Asignado y En pausa.
9. **Varios coordinadores por máquina y varias máquinas por coordinador** (ej. producción + mantenimiento). Se asignan en la ficha del usuario: "Máquinas que coordina".
10. **Notificaciones extra:** reporte anulado → operador; reasignado → técnico anterior. Además, la orden crítica asignada suena al técnico.
11. **Fusión de nodos** en el admin (acción "Fusionar nodos duplicados…").

---

## 3. Qué hay construido (resumen)

**Apps** (`apps/`): `usuarios`, `activos`, `tickets`, `notificaciones`, `agente` (solo modelo), `operador`, `tecnico`, `coordinador`, `core`.

**Funciones de servicio clave:**
- `apps/tickets/servicios.py` → `crear_ticket()` (idempotente por UUID) y `transicionar()` (única vía de cambio de estado).
- `apps/notificaciones/servicios.py` → `notificar()` (única función que crea avisos) y la matriz de quién recibe qué.
- `apps/activos/servicios.py` → sugerencias difusas, crear nodo de operador, `fusionar()`.
- `apps/tickets/sla.py` → semáforo de plazos (70 % / 100 %) y tiempo en pausa.

**Pantallas por rol** (menú fijo abajo en celular / arriba en PC):
- Operador: Reportar falla (mosaico con color por nivel) · Mis reportes · Cuenta.
- Técnico: Mis órdenes · Reportar falla · Mis reportes · Cuenta.
- Coordinador: Bandeja (4 columnas) · Máquinas (historial) · Plazos · Reportar · Cuenta.
- Administrador: Cuenta · Admin (importar Excel, árbol, fusión, usuarios, plazos).

**Comando programado:** `python manage.py revisar_sla` (en producción, cada 5 minutos con un timer de systemd; en local, `--repetir`).

---

## 4. Cómo correrlo en local (Windows)

```powershell
cd "C:\MV\I+D+I\tacora\tacora-mantenimiento"
.venv\Scripts\python manage.py runserver
```

En otra terminal, si se quieren avisos de plazos:

```powershell
.venv\Scripts\python manage.py revisar_sla --repetir
```

- Base de datos: `C:\MV\I+D+I\tacora\tacora-mantenimiento-data\mantenimiento.sqlite3` (fuera del código).
- Tailwind: `bin\tailwindcss.exe -i static/src/app.css -o static/css/app.css --minify` (después de cambiar plantillas). El CSS compilado sí va en Git.
- Para probar varios roles a la vez: un navegador distinto por sesión (Chrome normal, Chrome incógnito, Edge). Las ventanas de incógnito comparten una sola sesión.

---

## 5. Fase 7 — Lo que haremos mañana

### Parte A — La hago yo (Claude), en el repositorio
1. Carpeta `deploy/` con:
   - `mantenimiento.service` + `mantenimiento.socket` (Gunicorn con socket propio).
   - `mantenimiento-sla.service` + `.timer` (revisar plazos cada 5 min).
   - `mantenimiento-respaldo.service` + `.timer` + script (copia diaria con `sqlite3 .backup`, guardar 30 días).
   - `nginx-mantenimiento.conf` (bloque `server` para `tecnosur.mantenimiento.tacorapp.com`, estáticos servidos por Nginx).
2. Ajustes de producción: `gunicorn` en `requirements.txt`, `collectstatic`, registro de errores a archivo, `manage.py check --deploy` sin advertencias importantes.
3. `deploy/GUIA.md`: los comandos para el servidor, en orden y explicados.

### Parte B — En el servidor (con la guía, paso a paso)
1. Crear el repo privado en GitHub (ej. `mv-op/tacora-mantenimiento`) y hacer `git push`.
2. DNS: registro A `tecnosur.mantenimiento` → IP de la VM de Tacora.
3. En la VM: clonar, crear `.venv`, instalar, crear `.env` (permisos 600, `DEBUG=False`, `SECRET_KEY` nueva, `CLAVE_INICIAL` definitiva), carpeta de datos, `migrate`, `createsuperuser`.
4. Activar servicios y timers de systemd, el bloque de Nginx y `sudo certbot --nginx -d tecnosur.mantenimiento.tacorapp.com`.
5. Probar con un grupo pequeño en planta.

**Condición de cierre de la Fase 7:** el piloto opera una semana sin pérdida de reportes.

### Preguntas pendientes para empezar mañana
- ¿Qué sistema operativo tiene la VM? (en el servidor: `cat /etc/os-release`)
- ¿Quién entra por SSH al servidor: tú u otra persona?
- ¿Se pueden copiar el `.service` y el bloque de Nginx de Tacora? Así los archivos quedan iguales a lo que ya funciona (rutas, usuario del sistema, estilo).
- ¿Qué versión de Python tiene la VM? (`python3 --version`). En local usamos 3.13.
- ¿Nombre exacto del repositorio en GitHub y quién lo crea?

---

## 6. Pendientes que no son de la Fase 7

- Cargar el **Excel real** del árbol de Tecnosur (con la plantilla del admin) y ajustar la plantilla si hace falta.
- Revisión legal de los términos y la autorización de datos (Ley 1581).
- Definir la **contraseña inicial** definitiva para producción (va solo en el `.env` del servidor).
- En los PC de planta compartidos: desactivar el gestor de contraseñas del navegador por política de Windows.
- Ideas que quedaron mencionadas y no se hicieron: borrador en el equipo para el formulario de cierre del técnico; Web Push para avisar con la app cerrada.
