#!/usr/bin/env bash
# Reversión completa del despliegue (Linux): detiene y elimina contenedores,
# la red interna y los volúmenes de datos. Deja el sistema sin rastros.
#
#   ./scripts/clean.sh            # contenedores + red + volúmenes
#   ./scripts/clean.sh --images   # además, elimina las imágenes construidas
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--images" ]]; then
    docker compose down -v --remove-orphans --rmi local
else
    docker compose down -v --remove-orphans
fi
echo "Despliegue eliminado por completo."
