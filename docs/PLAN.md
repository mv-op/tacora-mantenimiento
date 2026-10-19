# Plan de desarrollo — CMMS Tecnosur Mantenimiento

Versión: 18 de octubre de 2026

## Resumen y decisiones de arquitectura

Se construye un CMMS nuevo e independiente de Tacora, con la misma estructura técnica, desplegado en tecnosur.mantenimiento.tacorapp.com. Sirve a cuatro roles: operador, coordinador, técnico y administrador. Las notificaciones son solo dentro de la aplicación, y toda la hora del sistema es la de Bogotá.

| Decisión | Qué se hace | Por qué |
| --- | --- | --- |
| Proyecto separado | Repositorio, base de datos y servicio propios | Escalar y mantener sin tocar Tacora |
| Misma pila que Tacora | Django 5, SQLite (base por defecto de Django), Nginx + Gunicorn + systemd en la VM de Tacora | Flujo de despliegue ya probado |
| Frontend | Plantillas Django + HTMX + Tailwind, sin `<select>` | Botones grandes para uso táctil en planta |
| Árbol de activos | Una sola tabla `NodoActivo` con `nivel` y `padre` | Merge, búsqueda e importación se escriben una vez |
| Historial para analítica | Tabla `EventoTicket` además de `django-simple-history` | Calcular MTTR, tiempos por estado y rechazos |
| SLA | Ajustable por el coordinador, en horas, calculado desde fechas | Crítica se mide en horas; los retrasos no se guardan |
| Anti-duplicados | UUID generado en el navegador + bloqueo del botón con HTMX | Evita tickets dobles por red inestable o reenvío offline |
| Acceso | Usuario + contraseña; contraseña inicial común con cambio obligatorio; cierre por inactividad | Simple de administrar, sin sesiones abiertas |
| Texto para IA | Texto libre crudo + metadatos; mínimo de caracteres; dictado por voz del teléfono | Datos útiles para LLM y búsqueda semántica |
| Agente | Primero reglas programadas; luego resumen con LLM | Más barato, confiable y auditable |

## Infraestructura y dominio

La aplicación corre como un servicio aparte en la misma VM de Tacora, con su propio archivo de base de datos SQLite, y queda en tecnosur.mantenimiento.tacorapp.com.

| Elemento | Configuración |
| --- | --- |
| Repositorio | Nuevo repo privado en GitHub (ej. `mv-op/tacora-mantenimiento`), separado de `tacora` |
| Servidor | Misma VM de Tacora; servicio systemd propio (`mantenimiento.service`), socket Gunicorn propio y bloque `server` propio en Nginx |
| Base de datos | SQLite (base por defecto de Django) en modo WAL, en una carpeta fuera del código |
| Zona horaria | `TIME_ZONE = "America/Bogota"` y `USE_TZ = True`; todo se muestra en hora Bogotá |
| Búsqueda difusa | Nombres normalizados + librería `rapidfuzz` en Python |
| Dominio | Registro DNS para `tecnosur.mantenimiento.tacorapp.com` apuntando a la IP de la VM |
| HTTPS | Certificado Let's Encrypt propio: sudo certbot --nginx -d tecnosur.mantenimiento.tacorapp.com, con renovación automática |
| Secretos | Archivo `.env` fuera del repo, permisos 600 |
| Tareas programadas | Timer de systemd que ejecuta comandos de Django (SLA, agente) |
| Respaldos | Copia diaria del archivo SQLite con `sqlite3 .backup` + snapshot de disco semanal |
| Flujo de trabajo | Igual que Tacora: editar en local con Claude Code → git push → git pull en servidor → reiniciar servicio |

Sobre SQLite: PostgreSQL es software libre y no necesita licencia, pero SQLite es suficiente para el volumen inicial de una planta. Si crecen los usuarios simultáneos, el cambio a PostgreSQL es de configuración y una migración de datos, no de código.

Sobre el dominio: `tecnosur.mantenimiento.tacorapp.com` es un subdominio gratuito de tacorapp.com y separa este producto de Tacora. Como tiene dos niveles, un certificado `*.tacorapp.com` no lo cubre; lleva su propio certificado. Para más clientes, el patrón es `cliente.mantenimiento.tacorapp.com`, y con muchos clientes conviene un solo certificado `*.mantenimiento.tacorapp.com`.

## Modelo de datos

El modelo se diseña completo desde la Fase 1, incluyendo lo que necesitan los dashboards y el agente, aunque esas pantallas lleguen después.

| Tabla | Campos clave | Para qué sirve |
| --- | --- | --- |
| `Usuario` (extiende `AbstractUser`) | rol, nombre visible, debe\_cambiar\_clave, intentos\_fallidos, bloqueado\_hasta (activo = `is_active` de Django) | Los cuatro roles y el primer login obligatorio |
| `AceptacionTerminos` | usuario, versión, fecha, IP, user agent | Cumplimiento legal y autorización de datos personales |
| `NodoActivo` | nombre, nombre\_normalizado, nivel (Máquina…Componente), padre, origen (Excel / operador), estado\_curaduría, is\_active, fusionado\_en | Árbol único de cinco niveles con soft-delete |
| `CoordinadorMaquina` | coordinador, máquina | Qué máquinas ve cada coordinador |
| `ReglaSLA` | criticidad, horas\_para\_asignar, horas\_para\_resolver, modificada\_por, activa | Semáforos y vencimientos, ajustables por el coordinador |
| `Ticket` | uuid\_cliente (único), nodo, descripción, criticidad, estado, reportado\_por, técnico, fechas por hito | El reporte y su estado actual |
| `EventoTicket` | ticket, tipo de transición, estado\_desde, estado\_hacia, actor, comentario, fecha | Línea de tiempo para auditoría y analítica |
| `CierreTecnico` | ticket, causa\_raíz, acción\_correctiva, repuestos, recomendación\_preventiva, intento (n.º) | Captura de conocimiento; un registro por intento si hay rechazo |
| `ContraReporte` | ticket, técnico, motivo, fecha, respuesta del coordinador | Pausas y bloqueos explicados en texto |
| `Notificacion` | destinatario, tipo, ticket, mensaje, prioridad, leída\_en, creada\_en | Bandeja de notificaciones en la app |
| `HallazgoAgente` | tipo de regla, nodo o ticket, severidad, detalle, estado (abierto / atendido) | Lo que detecta el agente de monitoreo |

Reglas de diseño:

- El árbol se carga desde una plantilla de Excel con una columna por nivel: Máquina, Unidad, Sistema, Equipo, Componente. Cada fila es una ruta; los niveles finales pueden quedar vacíos.
- La importación valida antes de guardar y muestra un resumen: nodos nuevos, existentes y filas con error.
- Lo que crean los operadores desde la app queda con estado de curaduría *pendiente*.
- `nombre_normalizado` (minúsculas, sin tildes ni signos) más `rapidfuzz` alimenta el autocompletado difuso.
- `django-simple-history` se aplica a `NodoActivo`, `Ticket` y `ReglaSLA` para la auditoría de cambios.
- Todas las fechas se guardan con zona horaria y se muestran en hora Bogotá.
- Los textos libres se guardan sin modificar, listos para análisis con LLM.

## Ciclo del ticket y SLA

Cada cambio de estado es una transición permitida y queda como un `EventoTicket` con actor, fecha y comentario.

```text
Reportado -> Asignado -> En proceso -> Resuelto (pendiente de validación) -> Cerrado
En proceso -> En pausa (contra-reporte del técnico) -> En proceso (reanuda)
Resuelto -> En proceso (coordinador rechaza)
Reportado -> Anulado (coordinador, con motivo)
```

Un rechazo devuelve el ticket a *En proceso* y obliga al técnico a escribir un nuevo cierre. El coordinador también puede anular un ticket duplicado o improcedente desde *Reportado*, con motivo obligatorio.

| Transición | Quién la hace | Qué exige |
| --- | --- | --- |
| Reportado → Asignado | Coordinador | Elegir técnico desde las tarjetas |
| Asignado → En proceso | Técnico | Botón "Iniciar" |
| En proceso → En pausa | Técnico | Motivo del contra-reporte en texto |
| En pausa → En proceso | Coordinador o técnico | Respuesta o reanudación |
| En proceso → Resuelto | Técnico | Los tres campos de cierre, con mínimo de caracteres |
| Resuelto → Cerrado | Coordinador | Validación |
| Resuelto → En proceso | Coordinador | Motivo del rechazo en texto |
| Reportado → Anulado | Coordinador | Motivo de anulación |

SLA propuesto como punto de partida. El coordinador lo ajusta desde su pantalla y cada cambio queda en el historial:

| Criticidad | Asignar antes de | Resolver antes de |
| --- | --- | --- |
| Crítica | 30 min | 8 h |
| Urgente | 2 h | 24 h |
| Importante | 8 h | 72 h |

El semáforo se calcula en cada consulta: verde hasta el 70 % del tiempo, amarillo hasta el 100 %, rojo vencido. El tiempo en pausa se registra aparte para que el análisis distinga espera de trabajo.

## Sistema de notificaciones

Las notificaciones viven solo dentro de la aplicación: una campana con contador, avisos emergentes y una bandeja. No se usa correo ni mensajería externa.

**Cómo funciona**

1. Cada transición de ticket y cada hallazgo del agente pasa por una función central `notificar()`. Ninguna vista crea notificaciones por su cuenta.
2. `notificar()` crea registros en `Notificacion` según la matriz de abajo, sin repetir: un solo aviso por destinatario, ticket, tipo y umbral.
3. El navegador consulta con HTMX cada 20 segundos (`hx-trigger="every 20s"`) un endpoint liviano que devuelve el contador y los avisos nuevos. Funciona con Gunicorn sin WebSockets.
4. Los avisos nuevos aparecen como tarjeta emergente. El título de la pestaña muestra el número pendiente, por ejemplo "(3) Mantenimiento".
5. Las notificaciones de criticidad *Crítica* y los SLA vencidos suenan y quedan fijas en pantalla hasta que alguien las marque como vistas.
6. Una tarea programada cada 5 minutos revisa los SLA y genera los avisos de "por vencer" (70 %) y "vencido" (100 %).

**Quién recibe qué**

| Evento | Operador | Coordinador | Técnico | Admin |
| --- | --- | --- | --- | --- |
| Nuevo reporte en sus máquinas | — | Sí | — | — |
| Reporte crítico | — | Sí, con sonido | — | — |
| Ticket asignado | Sí (su reporte) | — | Sí | — |
| Técnico inicia trabajo | Sí (su reporte) | — | — | — |
| Contra-reporte | — | Sí | — | — |
| Respuesta a contra-reporte | — | — | Sí | — |
| Resuelto, pendiente de validar | Sí (su reporte) | Sí | — | — |
| Cierre rechazado | — | — | Sí, con motivo | — |
| Ticket cerrado | Sí (su reporte) | — | Sí | — |
| SLA por vencer | — | Sí | Sí | — |
| SLA vencido | — | Sí, con sonido | Sí, con sonido | — |
| Nodo nuevo pendiente de curaduría | — | — | — | Sí |
| Hallazgo del agente | — | Sí | — | Sí |

Límite a tener en cuenta: si nadie tiene la aplicación abierta, nadie se entera. Se mitiga con una pantalla del coordinador siempre abierta en tablet o TV de planta. Si más adelante se necesita avisar con la app cerrada, el paso natural es Web Push del navegador, que no requiere correo.

## Pantallas por rol

Todas las pantallas usan botones grandes, sin `<select>`. Cada botón de envío se bloquea al primer toque y muestra "Enviando…".

Encabezado fijo en todas las pantallas: reloj grande con hora de Bogotá (horas y minutos, legible a distancia en celular y PC), el nombre del usuario y su rol, y la campana de notificaciones. La hora sale del servidor y el navegador solo la avanza, para que no dependa del reloj del dispositivo.

| Rol | Dispositivo | Pantallas |
| --- | --- | --- |
| Operador | Celular o PC | Mosaico de botones Máquina → Unidad → Sistema → Equipo → Componente, con "+ Crear nuevo" y autocompletado difuso al final de cada nivel · descripción en texto libre · tres botones de criticidad · "Mis reportes" con su estado · borrador guardado en `localStorage` y reenvío con UUID al volver la conexión |
| Coordinador | Escritorio o tablet | Bandeja de reportes de sus máquinas ordenada por criticidad y SLA · tarjetas de técnicos con número de tareas activas · respuesta a contra-reportes · validar o rechazar cierres · ajuste de SLA por criticidad · vista de historial por máquina |
| Técnico | Celular | "Mis órdenes" con cronómetro y semáforo · iniciar, pausar con contra-reporte, finalizar · formulario de cierre con tres campos, mínimo de caracteres y dictado por voz del teclado |
| Administrador | Django Admin | Usuarios y roles (crear con contraseña inicial, restablecer, desbloquear) · asignación coordinador–máquinas · importación del Excel · exportación a CSV · curaduría de nodos pendientes · acción de fusión (merge) · reglas SLA · aceptaciones de términos |

Ingreso: usuario y contraseña. Al crear un usuario se le asigna la contraseña inicial común (definida en `.env`); en su primer ingreso debe cambiarla por una propia (mínimo 8 caracteres, no solo números, distinta de la inicial) y aceptar los términos. Si la olvida, el administrador la restablece a la inicial. Tras 5 intentos fallidos se bloquea 15 minutos. Se le pide al navegador no guardar la contraseña; en PC compartidos conviene desactivar el gestor de contraseñas del navegador por política de Windows.

Cierre por inactividad: la sesión se cierra tras 15 minutos sin uso (ajustable en `.env`) y al cerrar el navegador. Las consultas automáticas, como la campana, no cuentan como uso. Un minuto antes aparece un aviso con botón "Seguir conectado". Si hay un reporte a medio escribir, el borrador se conserva en el navegador.

Fusión de nodos: el administrador elige el nodo correcto y el duplicado. En una sola transacción se mueven los tickets y los nodos hijos al nodo correcto, se marca el duplicado como inactivo con `fusionado_en`, y queda el registro en el historial.

## Fases de desarrollo

Cada fase termina con algo que funciona y se prueba antes de pasar a la siguiente. Se trabaja una fase a la vez.

1. **Base del proyecto**
   - Repo nuevo, proyecto Django, SQLite, zona horaria Bogotá, Tailwind y HTMX, configuración por `.env`.
   - Listo cuando: corre en local y existe el usuario administrador.
2. **Modelo de datos y admin**
   - Todas las tablas de la sección Modelo de datos, migraciones, admin con historial, plantilla e importación del árbol desde Excel, reglas SLA iniciales.
   - Listo cuando: el Excel real de Tecnosur carga sin errores y el árbol se ve en el admin.
3. **Acceso y cumplimiento**
   - Primer ingreso con contraseña inicial común, cambio obligatorio de contraseña, bloqueo por intentos, cierre por inactividad, aceptación de términos genéricos con registro (versión en `.env`), encabezado con reloj y usuario.
   - Listo cuando: un usuario nuevo no entra sin cambiar la contraseña y aceptar términos, y la sesión se cierra sola al quedar sin uso.
4. **Pantalla del operador**
   - Mosaico de botones, creación de nodos con autocompletado difuso, reporte con criticidad, borrador offline y UUID.
   - Listo cuando: un reporte enviado dos veces por red lenta crea un solo ticket.
5. **Coordinador y técnico**
   - Bandeja del coordinador, tarjetas de carga, ciclo completo de estados, cierre de tres campos, validar y rechazar.
   - Listo cuando: un ticket recorre todos los estados, incluido un rechazo, y cada paso queda en `EventoTicket`.
6. **Notificaciones**
   - Función `notificar()`, campana, avisos emergentes, sonido para críticos, tarea programada de SLA.
   - Listo cuando: cada fila de la matriz de notificaciones se prueba con un caso real.
7. **Despliegue piloto**
   - VM, servicio systemd, Nginx, certificado HTTPS, respaldos diarios, prueba con un grupo pequeño en planta.
   - Listo cuando: el piloto opera una semana sin pérdida de reportes.
8. **Dashboards**
   - Tickets por estado y criticidad, cumplimiento de SLA, MTTR, carga por técnico, máquinas y componentes con más fallas, exportación.
   - Listo cuando: el coordinador responde sus preguntas del mes sin pedir un Excel.
9. **Agente de monitoreo**
   - Reglas programadas: fallas repetidas en el mismo componente, tickets sin asignar, SLA vencidos, rechazos repetidos, nodos duplicados probables. Luego, resumen semanal en lenguaje natural con LLM sobre los textos de cierre.
   - Listo cuando: cada hallazgo aparece como notificación y en una bandeja propia.

## Decisiones pendientes

- [x] Base de datos: SQLite, la de Django por defecto.
- [x] Servidor: misma VM de Tacora al inicio.
- [x] SLA: ajustable por el coordinador.
- [x] Términos de uso: texto genérico en la primera versión.
- [x] Acceso: usuario + contraseña (sin PIN), contraseña inicial común con cambio obligatorio, cierre por inactividad. Decidido el 19 de octubre de 2026.
- [x] Dominio: tecnosur.mantenimiento.tacorapp.com.
- [ ] Enviar el Excel del árbol de Tecnosur, o usar la plantilla que se genera en la Fase 2.
- [ ] Más adelante: revisión legal de los términos y la autorización de datos (Ley 1581).
