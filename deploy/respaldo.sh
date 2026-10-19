#!/bin/sh
# Copia segura de la base SQLite (funciona con la app encendida) y borra las de más de 30 días.
set -eu

DATOS=/home/imrodriguez/tacora-mantenimiento-data
DESTINO="$DATOS/respaldos"
ARCHIVO="$DESTINO/mantenimiento-$(TZ=America/Bogota date +%F).sqlite3"

mkdir -p "$DESTINO"
sqlite3 "$DATOS/mantenimiento.sqlite3" ".backup '$ARCHIVO'"
gzip -f "$ARCHIVO"
find "$DESTINO" -name 'mantenimiento-*.sqlite3.gz' -mtime +30 -delete
echo "Respaldo listo: $ARCHIVO.gz"
