# Escenarios de prueba — Fase 2 (Windows).
#
# Escenario 1: operacion normal (registro + replicacion + consulta).
# Escenario 2: caida del Servidor 2, el Servidor 1 sigue atendiendo y,
#              al reactivarse, el Servidor 2 se resincroniza.
#
# Si la politica de ejecucion lo bloquea:
#   powershell -ExecutionPolicy Bypass -File .\tests\escenarios.ps1
#
# Al terminar, el despliegue queda activo para capturar evidencias;
# reviertalo con scripts\clean.ps1.
#
# Nota: cada invocacion del cliente esta escrita literalmente (sin
# funciones ni splatting de argumentos) y el archivo usa solo caracteres
# ASCII: asi evita problemas de paso de argumentos y de codificacion en
# Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Wait-For([int]$Seconds, [string]$Description) {
    Write-Host ""
    Write-Host ">>> Esperando $Seconds s ($Description)..."
    Start-Sleep -Seconds $Seconds
}

Write-Host "===== ESCENARIO 1: operacion normal ====="
Write-Host ">>> Levantando bases de datos y servidores..."
docker compose up -d --build db1 db2 server1 server2
if ($LASTEXITCODE -ne 0) { throw "docker compose up fallo" }
Wait-For 20 "arranque de PostgreSQL y de los servidores"

Write-Host ">>> Estado de los contenedores:"
docker compose ps

Write-Host ">>> 1.1 Crear un registro a traves del Servidor 1:"
docker compose run --rm --no-deps -T client python3 client.py create --payload "Primer registro (via servidor 1)" --server 1

Write-Host ">>> 1.2 Consultarlo a traves del Servidor 2 (evidencia de replicacion):"
docker compose run --rm --no-deps -T client python3 client.py list --server 2

Write-Host ">>> 1.3 Estado de ambos servidores y de su vision del par:"
docker compose run --rm --no-deps -T client python3 client.py status

Write-Host ""
Write-Host "===== ESCENARIO 2: caida y recuperacion del Servidor 2 ====="
Write-Host ">>> 2.1 Deteniendo el Servidor 2..."
docker compose stop server2
Wait-For 8 "deteccion de la caida por el heartbeat"

Write-Host ">>> 2.2 Crear registros con el Servidor 2 caido:"
Write-Host ">>> (el primero pide server2 a proposito: el cliente debe conmutar a server1)"
docker compose run --rm --no-deps -T client python3 client.py create --payload "Registro creado con server2 caido (1)" --server 2
docker compose run --rm --no-deps -T client python3 client.py create --payload "Registro creado con server2 caido (2)" --server 1

Write-Host ">>> 2.3 El Servidor 1 sigue atendiendo con normalidad:"
docker compose run --rm --no-deps -T client python3 client.py list --server 1
docker compose run --rm --no-deps -T client python3 client.py status

Write-Host ">>> 2.4 Reactivando el Servidor 2..."
docker compose start server2
Wait-For 25 "heartbeat, deteccion del par y resincronizacion"

Write-Host ">>> 2.5 El Servidor 2 ya tiene los registros creados durante su caida:"
docker compose run --rm --no-deps -T client python3 client.py list --server 2

Write-Host ">>> 2.6 Estado final de los servidores:"
docker compose run --rm --no-deps -T client python3 client.py status

Write-Host ">>> 2.7 Historial local del cliente (SQLite):"
docker compose run --rm --no-deps -T client python3 client.py history --limit 15

Write-Host ""
Write-Host ">>> Trazas del canal de sincronia (logs):"
docker compose logs server1 server2 | Select-String "\[sync\]" | Select-Object -Last 20

Write-Host ""
Write-Host "===== Escenarios terminados. ====="
Write-Host "El despliegue queda activo para las evidencias."
Write-Host "Para revertir: scripts\clean.ps1 (Windows) o scripts/clean.sh (Linux)."
