# CMMS Tecnosur Mantenimiento

Sistema de gestión de mantenimiento (CMMS) para la planta de Tecnosur.
Aplicación independiente de Tacora, con la misma estructura técnica.

El plan completo está en `docs/PLAN.md`. Léelo antes de empezar cualquier tarea.

## Cómo trabajar conmigo

- Responde siempre en español.
- Explica en pasos cortos y calmados, uno a la vez.
- Trabajamos una fase del plan a la vez. Al terminar una fase, muestra cómo probarla y espera mi confirmación antes de seguir.
- Antes de cambios grandes (modelos, migraciones, borrar archivos), dime qué vas a hacer y por qué.
- Cuando algo del plan no tenga sentido técnico, dímelo antes de implementarlo.

## Pila técnica

- Python 3, Django 5
- Base de datos: SQLite (la de Django por defecto), en modo WAL, archivo fuera del código
- Frontend: plantillas Django + HTMX + Tailwind CSS
- Historial: `django-simple-history`
- Búsqueda difusa: `rapidfuzz`
- Excel: `openpyxl`
- Configuración por `.env` (nunca subir `.env` a Git)

## Reglas del proyecto

- Zona horaria: `TIME_ZONE = "America/Bogota"`, `USE_TZ = True`. Todo se muestra en hora Bogotá.
- Interfaz en español, pensada para celular y PC.
- Sin `<select>`: toda elección se hace con botones grandes o tarjetas.
- Todo botón de envío se bloquea al primer clic y muestra "Enviando…".
- Encabezado fijo en todas las pantallas: reloj grande (hora Bogotá), nombre y rol del usuario, campana de notificaciones.
- Ingreso con usuario + contraseña. Contraseña inicial común (`CLAVE_INICIAL` en `.env`) que cada usuario cambia en su primer ingreso. Bloqueo de 15 min tras 5 intentos fallidos. La sesión se cierra por inactividad (15 min por defecto, `SESION_INACTIVIDAD_MINUTOS` en `.env`) y al cerrar el navegador.
- Árbol de activos en una sola tabla `NodoActivo` con `nivel` y `padre` (Máquina → Unidad → Sistema → Equipo → Componente). Nunca se borra: se desactiva con `is_active=False`.
- Cada cambio de estado de un ticket pasa por una función de servicio que valida la transición y crea un `EventoTicket`. Las vistas no cambian el estado directamente.
- Todas las notificaciones se crean desde una sola función `notificar()`. Solo notificaciones dentro de la app (sin correo).
- Los textos libres (descripción, causa raíz, acción correctiva, recomendación) se guardan sin modificar.
- Los tiempos de SLA y retrasos se calculan desde las fechas; no se guardan contadores.

## Despliegue

- Dominio: `tecnosur.mantenimiento.tacorapp.com`
- Misma VM de Tacora: Nginx + Gunicorn + systemd, con servicio, socket y bloque Nginx propios.
- Flujo: editar en local → `git push` → `git pull` en el servidor → reiniciar el servicio.
