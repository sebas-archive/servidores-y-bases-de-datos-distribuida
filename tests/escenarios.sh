#!/usr/bin/env bash
# Escenarios de prueba — Fase 2 (Linux).
#
# Escenario 1: operación normal (registro + replicación + consulta).
# Escenario 2: caída del Servidor 2, el Servidor 1 sigue atendiendo y,
#              al reactivarse, el Servidor 2 se resincroniza.
#
# Al terminar, el despliegue queda activo para capturar evidencias;
# reviértalo con scripts/clean.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

wait_for() { echo; echo ">>> Esperando $1 s ($2)..."; sleep "$1"; }
# --no-deps: el cliente no debe arrancar ni reiniciar servidores por su
# cuenta (compose arranca las dependencias de `run`; eso arruinaría el
# escenario de caída al "resucitar" al Servidor 2).
client() { docker compose run --rm --no-deps -T client python3 client.py "$@"; }

echo "===== ESCENARIO 1: operación normal ====="
echo ">>> Levantando bases de datos y servidores..."
docker compose up -d --build db1 db2 server1 server2
wait_for 20 "arranque de PostgreSQL y de los servidores"

echo ">>> Estado de los contenedores:"
docker compose ps

echo ">>> 1.1 Crear un registro a través del Servidor 1:"
client create --payload "Primer registro (vía servidor 1)" --server 1

echo ">>> 1.2 Consultarlo a través del Servidor 2 (evidencia de replicación):"
client list --server 2

echo ">>> 1.3 Estado de ambos servidores y de su visión del par:"
client status

echo
echo "===== ESCENARIO 2: caída y recuperación del Servidor 2 ====="
echo ">>> 2.1 Deteniendo el Servidor 2..."
docker compose stop server2
wait_for 8 "detección de la caída por el heartbeat"

echo ">>> 2.2 Crear registros con el Servidor 2 caído:"
echo ">>> (el primero pide server2 a propósito: el cliente debe conmutar a server1)"
client create --payload "Registro creado con server2 caído (1)" --server 2
client create --payload "Registro creado con server2 caído (2)" --server 1

echo ">>> 2.3 El Servidor 1 sigue atendiendo con normalidad:"
client list --server 1
client status

echo ">>> 2.4 Reactivando el Servidor 2..."
docker compose start server2
wait_for 25 "heartbeat, detección del par y resincronización"

echo ">>> 2.5 El Servidor 2 ya tiene los registros creados durante su caída:"
client list --server 2

echo ">>> 2.6 Estado final de los servidores:"
client status

echo ">>> 2.7 Historial local del cliente (SQLite):"
client history --limit 15

echo
echo ">>> Trazas del canal de sincronía (logs):"
docker compose logs server1 server2 | grep "\[sync\]" | tail -20 || true

echo
echo "===== Escenarios terminados. ====="
echo "El despliegue queda activo para las evidencias."
echo "Para revertir: scripts/clean.sh (Linux) o scripts/clean.ps1 (Windows)."
