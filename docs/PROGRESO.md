# Progreso del proyecto — CMMS Tecnosur Mantenimiento

Última actualización: 19 de octubre de 2026.
Siguiente sesión: **Fase 7 — probar en navegador y cargar datos del piloto** (DNS y HTTPS ya listos). Ver sección 5.

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
| 7. Despliegue piloto | ⏳ **En curso**: app en https://tecnosur.mantenimiento.tacorapp.com, falta probar y cargar datos | `fcd9c76` … `ac33460` |
| 8. Dashboards | Pendiente | — |
| 9. Agente de monitoreo | Pendiente | — |

- 132 pruebas automáticas, todas pasan: `.venv\Scripts\python manage.py test apps`
- Repositorio en GitHub: https://github.com/mv-op/tacora-mantenimiento (rama `main`). **Hoy está público** (ver pendientes).

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

## 5. Fase 7 — Despliegue (estado al 19 de octubre, tarde)

La guía completa y al día está en `deploy/GUIA.md`.

### El servidor (contexto)
- VM de Google Cloud `tacora-tq-instance-01`, **Debian 13**, Python 3.13.5, IP pública **34.174.134.168**.
- Entra por SSH el usuario (`imrodriguez`). Ahí también corre **Tacora**, que **no se toca**:
  `tacora.service` (Gunicorn en `0.0.0.0:8000`, sin socket), `/etc/nginx/sites-available/tacora`, `~/tacora_django`,
  dominio `tecnosur.tacorapp.com`.
- Reglas del usuario para el servidor: todo lo nuevo se llama `tacora-mantenimiento`; mostrar y esperar aprobación
  antes de tocar archivos del sistema; `sudo nginx -t` antes de aplicar Nginx; respaldo previo en `~/backups/AAAA-MM-DD/`;
  avisar antes de cualquier `apt install`; si algo falla, mostrar el error completo y consultar antes de arreglar.

### Lo que ya quedó funcionando en la VM
| Pieza | Dónde | Comprobado |
| --- | --- | --- |
| Código | `~/tacora-mantenimiento` (clonado de GitHub) | ✅ |
| Entorno Python | `~/tacora-mantenimiento/.venv` | ✅ |
| `.env` de producción | `~/tacora-mantenimiento/.env` (600), `SECRET_KEY` y `CLAVE_INICIAL` nuevas | ✅ |
| Base de datos | `~/tacora-mantenimiento-data/mantenimiento.sqlite3` (migrada, superusuario creado) | ✅ |
| `check --deploy` | Solo W005 y W021 (se dejan así) | ✅ |
| Socket + servicio | `tacora-mantenimiento.socket` → `/run/tacora-mantenimiento.sock` (dueño `www-data`, 600) y `tacora-mantenimiento.service` | ✅ responde `301` |
| Nginx | `/etc/nginx/sites-available/tacora-mantenimiento` + enlace en `sites-enabled` (80 → 301 a https; 443 con certificado) | ✅ `nginx -t` ok; Tacora sigue en `302` |
| DNS | Registro A `tecnosur.mantenimiento` → `34.174.134.168` (Hostinger) | ✅ |
| HTTPS | Certificado Let's Encrypt propio `tecnosur.mantenimiento.tacorapp.com` (vence 2027-01-18, renovación automática). Respaldo previo: `~/backups/2026-10-19/tacora-mantenimiento.antes-certbot` | ✅ https `302` → `/ingresar/` |
| Plazos | `tacora-mantenimiento-sla.timer`, cada 5 min | ✅ |
| Respaldo | `tacora-mantenimiento-respaldo.timer`, 2:00 a. m. Bogotá, 30 días, en `~/tacora-mantenimiento-data/respaldos/` | ✅ probado a mano |
| Respaldo de Nginx previo | `~/backups/2026-10-19/` | ✅ |

### Cambios respecto a lo planeado (por lo que se encontró en el servidor)
1. **Nombres con prefijo `tacora-mantenimiento`** en servicio, socket, timers y Nginx (regla del usuario).
2. **Socket con unidad `.socket` de systemd**: Gunicorn corre como `imrodriguez` y no puede crear archivos en `/run`.
3. **Estáticos con WhiteNoise** (los sirve Django): la carpeta personal es `drwx------` y Nginx (`www-data`) no puede
   leerla. Se eligió esto en vez de abrir permisos del home. Tras cada `collectstatic` hay que reiniciar el servicio.
4. **Respaldo con la librería sqlite3 de Python**: el servidor no tiene el programa `sqlite3`.
5. **Errores al journal**: `journalctl -u tacora-mantenimiento`.

### Lo que falta
1. Probar en el navegador (celular y PC): ingreso con el superusuario, admin, pantallas.
2. Cargar el Excel del árbol, crear usuarios del piloto y coordinadores, revisar plazos.
3. Programar snapshot semanal del disco en Google Cloud.
4. Piloto con un grupo pequeño. **Cierre de la Fase 7:** una semana sin pérdida de reportes.

### Plan B si el DNS se demora (el usuario pidió no usarlo por ahora)
Nombre gratuito con HTTPS: `tecnosur-mantenimiento.34-174-134-168.sslip.io`. Requiere agregarlo en `ALLOWED_HOSTS` y
`CSRF_TRUSTED_ORIGINS` del `.env`, en el `server_name` de Nginx, y correr certbot para ese nombre. No toca Tacora.
Se descartó: entrar solo por IP (sin HTTPS, habría que apagar la seguridad) y colgarla de `tecnosur.tacorapp.com`
(obliga a editar el Nginx de Tacora y las cookies de sesión chocan).

---

## 6. Pendientes que no son de la Fase 7

- Cargar el **Excel real** del árbol de Tecnosur (con la plantilla del admin) y ajustar la plantilla si hace falta.
- Revisión legal de los términos y la autorización de datos (Ley 1581).
- En los PC de planta compartidos: desactivar el gestor de contraseñas del navegador por política de Windows.
- **Repositorio público**: se puso público para clonar fácil. No tiene secretos, pero `docs/PROGRESO.md` menciona la clave inicial de local. Opción: volverlo privado y guardar un token de solo lectura en el servidor para los `git pull`.
- **Tacora expone el puerto 8000 a internet** (Gunicorn en `0.0.0.0:8000` y firewall abierto): se puede entrar saltando Nginx y HTTPS. Revisar aparte, sin mezclarlo con este despliegue.
- Ideas que quedaron mencionadas y no se hicieron: borrador en el equipo para el formulario de cierre del técnico; Web Push para avisar con la app cerrada.
