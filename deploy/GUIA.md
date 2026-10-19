# Guía de despliegue — tacora-mantenimiento

Servidor: VM de Tacora (Debian 13, Python 3.13), usuario `imrodriguez`.
Dominio: `tecnosur.mantenimiento.tacorapp.com`.

**Convive con Tacora en la misma VM. Nada de esta guía toca a Tacora** (`tacora.service`, `/etc/nginx/sites-available/tacora`,
`~/tacora_django`, puerto 8000). Todo lo nuevo lleva el nombre `tacora-mantenimiento`.

| Qué | Dónde |
| --- | --- |
| Código | `/home/imrodriguez/tacora-mantenimiento` |
| Entorno de Python | `/home/imrodriguez/tacora-mantenimiento/.venv` |
| Datos (base SQLite y respaldos) | `/home/imrodriguez/tacora-mantenimiento-data` |
| Secretos | `/home/imrodriguez/tacora-mantenimiento/.env` (permisos 600) |
| Socket de Gunicorn | `/run/tacora-mantenimiento.sock` (lo crea systemd) |
| Servicio y socket | `tacora-mantenimiento.service`, `tacora-mantenimiento.socket` |
| Timers | `tacora-mantenimiento-sla.timer`, `tacora-mantenimiento-respaldo.timer` |
| Nginx | `/etc/nginx/sites-available/tacora-mantenimiento` |

Haz los pasos en orden. Cada uno dice cómo comprobar que salió bien.

---

## 1. Traer el código y crear el entorno de Python

```bash
cd ~
git clone https://github.com/mv-op/tacora-mantenimiento.git
cd tacora-mantenimiento
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x deploy/respaldo.sh
```

No hace falta `apt install`: `python3-venv` ya está en el servidor, y el respaldo usa la librería sqlite3 de Python
(no necesita el programa `sqlite3` del sistema).

---

## 2. Archivo `.env`

```bash
cd ~/tacora-mantenimiento
cp .env.example .env
chmod 600 .env
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"   # copia el resultado
nano .env
```

Deja así los valores:

- `SECRET_KEY` = la clave que acabas de generar (nueva, distinta de la de local y de la de Tacora).
- `DEBUG=False`
- `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`: ya vienen bien.
- `DATA_DIR=/home/imrodriguez/tacora-mantenimiento-data`
- `CLAVE_INICIAL` = la contraseña inicial definitiva (mínimo 8 caracteres, no solo números, **distinta de la de local**).

Guardar en nano: `Ctrl + O`, `Enter`, `Ctrl + X`.

---

## 3. Base de datos, estáticos y administrador

```bash
cd ~/tacora-mantenimiento
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py check --deploy
```

Comprobar:
- `migrate` crea `~/tacora-mantenimiento-data/mantenimiento.sqlite3`.
- `check --deploy` solo muestra W005 y W021 (subdominios y precarga de HSTS); esas dos se dejan así.

---

## 4. Estáticos (CSS y JavaScript)

No requiere nada. La carpeta personal es `drwx------` y Nginx (`www-data`) no puede leerla, así que los estáticos los
sirve Django con WhiteNoise. Nginx solo pasa las peticiones por el socket. Por eso, después de cada
`collectstatic` hay que reiniciar el servicio.

---

## 5. Respaldo previo

Antes de los pasos con `sudo`, una copia de lo que ya existe en Nginx (no se va a tocar, es por seguridad):

```bash
mkdir -p ~/backups/$(date +%F)
sudo cp -a /etc/nginx/sites-available ~/backups/$(date +%F)/nginx-sites-available
sudo cp -a /etc/nginx/sites-enabled ~/backups/$(date +%F)/nginx-sites-enabled
```

---

## 6. Servicio y socket de la aplicación

Archivos **nuevos** en `/etc/systemd/system/`: `tacora-mantenimiento.socket` y `tacora-mantenimiento.service`.

```bash
cd ~/tacora-mantenimiento
sudo cp deploy/tacora-mantenimiento.socket deploy/tacora-mantenimiento.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tacora-mantenimiento.socket
sudo systemctl enable --now tacora-mantenimiento.service
sudo systemctl status tacora-mantenimiento
```

Comprobar:
- `status` dice `active (running)`.
- `ls -l /run/tacora-mantenimiento.sock` muestra el socket con dueño `www-data`.
- `sudo curl --unix-socket /run/tacora-mantenimiento.sock -s -o /dev/null -w "%{http_code}\n" -H "Host: tecnosur.mantenimiento.tacorapp.com" http://localhost/`
  devuelve `301` (la app responde y redirige a HTTPS).

Si falla: `journalctl -u tacora-mantenimiento -n 50 --no-pager`.

---

## 7. DNS

**Avisar antes de este paso.** Registro **A** `tecnosur.mantenimiento` → IP pública de la VM (la misma de `tecnosur.tacorapp.com`).

Comprobar (puede tardar unos minutos): `getent hosts tecnosur.mantenimiento.tacorapp.com` devuelve la IP de la VM.

---

## 8. Nginx y HTTPS

Archivo **nuevo** `/etc/nginx/sites-available/tacora-mantenimiento` y su enlace en `sites-enabled`.

```bash
cd ~/tacora-mantenimiento
sudo cp deploy/nginx-tacora-mantenimiento.conf /etc/nginx/sites-available/tacora-mantenimiento
sudo ln -s /etc/nginx/sites-available/tacora-mantenimiento /etc/nginx/sites-enabled/tacora-mantenimiento
sudo nginx -t
```

Solo si `nginx -t` dice `syntax is ok` y `test is successful`:

```bash
sudo systemctl reload nginx
```

Con el DNS ya apuntando a la VM, certificado propio (no reutiliza el de Tacora):

```bash
sudo certbot --nginx -d tecnosur.mantenimiento.tacorapp.com
```

Certbot pregunta si redirigir HTTP a HTTPS: responder que **sí**. Solo modifica el archivo `tacora-mantenimiento`.

Comprobar:
- `https://tecnosur.mantenimiento.tacorapp.com` muestra la pantalla de ingreso con candado.
- `https://tecnosur.tacorapp.com` (Tacora) sigue funcionando igual.

---

## 9. Timers: plazos y respaldo

Archivos **nuevos** en `/etc/systemd/system/`.

```bash
cd ~/tacora-mantenimiento
sudo cp deploy/tacora-mantenimiento-sla.service deploy/tacora-mantenimiento-sla.timer /etc/systemd/system/
sudo cp deploy/tacora-mantenimiento-respaldo.service deploy/tacora-mantenimiento-respaldo.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tacora-mantenimiento-sla.timer tacora-mantenimiento-respaldo.timer
```

Probarlos una vez a mano:

```bash
sudo systemctl start tacora-mantenimiento-sla
journalctl -u tacora-mantenimiento-sla -n 5 --no-pager      # "... tickets revisados · ... avisos nuevos"
sudo systemctl start tacora-mantenimiento-respaldo
ls -lh ~/tacora-mantenimiento-data/respaldos/               # aparece mantenimiento-AAAA-MM-DD.sqlite3.gz
systemctl list-timers 'tacora-mantenimiento*'               # próxima ejecución de cada uno
```

El respaldo corre a las 2:00 a. m. (hora Bogotá) y guarda 30 días. El snapshot semanal del disco se programa en la
consola de Google Cloud (Compute Engine → Snapshots → Crear programación de instantáneas).

---

## 10. Primeros datos

En `https://tecnosur.mantenimiento.tacorapp.com/admin/`:

1. Importar el árbol de activos (Excel con la plantilla).
2. Crear los usuarios del piloto y asignar las máquinas a cada coordinador.
3. Revisar los plazos (SLA).

---

## Actualizar después de un cambio

En tu PC: `git push`. En el servidor:

```bash
cd ~/tacora-mantenimiento
git pull
.venv/bin/pip install -r requirements.txt     # solo si cambió requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart tacora-mantenimiento
```

## Comandos útiles

| Para | Comando |
| --- | --- |
| Ver errores de la app | `journalctl -u tacora-mantenimiento -n 100 --no-pager` |
| Seguir errores en vivo | `journalctl -u tacora-mantenimiento -f` |
| Reiniciar la app | `sudo systemctl restart tacora-mantenimiento` |
| Ver los timers | `systemctl list-timers 'tacora-mantenimiento*'` |

## Restaurar un respaldo

```bash
sudo systemctl stop tacora-mantenimiento
cd ~/tacora-mantenimiento-data
mv mantenimiento.sqlite3 mantenimiento.sqlite3.antes
rm -f mantenimiento.sqlite3-wal mantenimiento.sqlite3-shm
gunzip -c respaldos/mantenimiento-AAAA-MM-DD.sqlite3.gz > mantenimiento.sqlite3
sudo systemctl start tacora-mantenimiento
```
