# Guía de despliegue — CMMS Tecnosur Mantenimiento

Servidor: VM de Tacora (Debian 13, Python 3.13), usuario `imrodriguez`.
Dominio: `tecnosur.mantenimiento.tacorapp.com`.

| Qué | Dónde |
| --- | --- |
| Código | `/home/imrodriguez/tacora-mantenimiento` |
| Datos (base SQLite y respaldos) | `/home/imrodriguez/tacora-mantenimiento-data` |
| Secretos | `/home/imrodriguez/tacora-mantenimiento/.env` (permisos 600) |
| Socket de Gunicorn | `/run/mantenimiento/gunicorn.sock` |

Haz los pasos en orden. Cada uno dice cómo comprobar que salió bien.

---

## 0. Antes de empezar (en tu PC)

1. Crear el repositorio **privado** en GitHub, vacío (sin README).
2. Subir el código:

   ```powershell
   git remote add origin git@github.com:<cuenta>/tacora-mantenimiento.git
   git push -u origin main
   ```

3. DNS: registro **A** `tecnosur.mantenimiento` → IP pública de la VM (la misma de `tecnosur.tacorapp.com`).

   Comprobar (puede tardar unos minutos): `nslookup tecnosur.mantenimiento.tacorapp.com` devuelve la IP de la VM.

---

## 1. Programas del sistema

```bash
sudo apt update
sudo apt install -y sqlite3 python3-venv git
```

Comprobar: `sqlite3 --version` y `python3 --version` (3.13).

---

## 2. Traer el código

El servidor necesita permiso para leer el repo privado. Si Tacora ya usa una llave SSH con GitHub, sirve la misma
(`ssh -T git@github.com` debe saludarte con tu usuario).

```bash
cd ~
git clone git@github.com:<cuenta>/tacora-mantenimiento.git
cd tacora-mantenimiento
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x deploy/respaldo.sh
```

---

## 3. Archivo `.env`

```bash
cp .env.example .env
chmod 600 .env
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(50))"   # copia el resultado
nano .env
```

Deja así los valores:

- `SECRET_KEY` = la clave que acabas de generar (nueva, distinta de la de local).
- `DEBUG=False`
- `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`: ya vienen bien.
- `DATA_DIR=/home/imrodriguez/tacora-mantenimiento-data`
- `CLAVE_INICIAL` = la contraseña inicial definitiva (mínimo 8 caracteres, no solo números).

Guardar en nano: `Ctrl + O`, `Enter`, `Ctrl + X`.

---

## 4. Base de datos, estáticos y administrador

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py check --deploy
```

Comprobar:
- `migrate` crea `~/tacora-mantenimiento-data/mantenimiento.sqlite3`.
- `check --deploy` solo muestra W005 y W021 (subdominios y precarga de HSTS); esas dos se dejan así.

---

## 5. Permisos para que Nginx lea los estáticos

Nginx (usuario `www-data`) debe poder entrar a la carpeta personal. Tacora ya funciona así, pero hay que confirmarlo:

```bash
namei -l /home/imrodriguez/tacora-mantenimiento/staticfiles/css/app.css
```

Cada carpeta de la lista debe tener `x` para "otros" (por ejemplo `drwxr-x--x` o `drwxr-xr-x`).
Si `/home/imrodriguez` sale `drwx------`, corre `chmod o+x /home/imrodriguez`.

---

## 6. Servicio de la aplicación

```bash
sudo cp deploy/mantenimiento.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mantenimiento
sudo systemctl status mantenimiento
```

Comprobar: dice `active (running)` y existe `/run/mantenimiento/gunicorn.sock`.
Si falla: `journalctl -u mantenimiento -n 50`.

---

## 7. Nginx y HTTPS

```bash
sudo cp deploy/nginx-mantenimiento.conf /etc/nginx/sites-available/mantenimiento
sudo ln -s /etc/nginx/sites-available/mantenimiento /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

`nginx -t` debe decir `syntax is ok` y `test is successful`. Solo entonces se hace el `reload`.
Este archivo es nuevo y no toca el de Tacora.

Con el DNS ya apuntando a la VM:

```bash
sudo certbot --nginx -d tecnosur.mantenimiento.tacorapp.com
```

Certbot pregunta si redirigir HTTP a HTTPS: responde que **sí**.

Comprobar: abrir `https://tecnosur.mantenimiento.tacorapp.com` en el navegador; aparece la pantalla de ingreso con candado.
Y que Tacora sigue bien: `https://tecnosur.tacorapp.com`.

---

## 8. Timers: plazos y respaldo

```bash
sudo cp deploy/mantenimiento-sla.service deploy/mantenimiento-sla.timer /etc/systemd/system/
sudo cp deploy/mantenimiento-respaldo.service deploy/mantenimiento-respaldo.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mantenimiento-sla.timer mantenimiento-respaldo.timer
```

Probarlos una vez a mano:

```bash
sudo systemctl start mantenimiento-sla
journalctl -u mantenimiento-sla -n 5           # "... tickets revisados · ... avisos nuevos"
sudo systemctl start mantenimiento-respaldo
ls -lh ~/tacora-mantenimiento-data/respaldos/  # aparece mantenimiento-AAAA-MM-DD.sqlite3.gz
systemctl list-timers 'mantenimiento*'         # muestra la próxima ejecución de cada uno
```

El respaldo corre a las 2:00 a. m. (hora Bogotá) y guarda 30 días. El snapshot semanal del disco se programa en la
consola de Google Cloud (Compute Engine → Snapshots → Crear programación de instantáneas).

---

## 9. Primeros datos

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
sudo systemctl restart mantenimiento
```

## Comandos útiles

| Para | Comando |
| --- | --- |
| Ver errores de la app | `journalctl -u mantenimiento -n 100` |
| Seguir errores en vivo | `journalctl -u mantenimiento -f` |
| Reiniciar la app | `sudo systemctl restart mantenimiento` |
| Ver los timers | `systemctl list-timers 'mantenimiento*'` |

## Restaurar un respaldo

```bash
sudo systemctl stop mantenimiento
cd ~/tacora-mantenimiento-data
mv mantenimiento.sqlite3 mantenimiento.sqlite3.antes
rm -f mantenimiento.sqlite3-wal mantenimiento.sqlite3-shm
gunzip -c respaldos/mantenimiento-AAAA-MM-DD.sqlite3.gz > mantenimiento.sqlite3
sudo systemctl start mantenimiento
```
