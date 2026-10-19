#!/bin/sh
# Copia segura de la base SQLite (funciona con la app encendida) y borra las de más de 30 días.
# Usa la librería sqlite3 del Python de la app, así no depende del programa sqlite3 del sistema.
set -eu

APP=/home/imrodriguez/tacora-mantenimiento
DATOS=/home/imrodriguez/tacora-mantenimiento-data
BASE="$DATOS/mantenimiento.sqlite3"
DESTINO="$DATOS/respaldos"
ARCHIVO="$DESTINO/mantenimiento-$(TZ=America/Bogota date +%F).sqlite3"

test -f "$BASE"
mkdir -p "$DESTINO"
"$APP/.venv/bin/python" -c '
import sqlite3, sys
origen = sqlite3.connect(sys.argv[1])
copia = sqlite3.connect(sys.argv[2])
origen.backup(copia)
copia.close()
origen.close()
' "$BASE" "$ARCHIVO"
gzip -f "$ARCHIVO"
find "$DESTINO" -name 'mantenimiento-*.sqlite3.gz' -mtime +30 -delete
echo "Respaldo listo: $ARCHIVO.gz"
