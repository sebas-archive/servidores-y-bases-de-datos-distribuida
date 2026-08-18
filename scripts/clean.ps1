# Reversión completa del despliegue (Windows): detiene y elimina contenedores,
# la red interna y los volúmenes de datos. Deja el sistema sin rastros.
#
#   .\scripts\clean.ps1           # contenedores + red + volúmenes
#   .\scripts\clean.ps1 -Images   # además, elimina las imágenes construidas
#
# Si la política de ejecución lo bloquea:
#   powershell -ExecutionPolicy Bypass -File .\scripts\clean.ps1
param([switch]$Images)

Set-Location (Split-Path $PSScriptRoot -Parent)

if ($Images) {
    docker compose down -v --remove-orphans --rmi local
} else {
    docker compose down -v --remove-orphans
}
Write-Host "Despliegue eliminado por completo."
