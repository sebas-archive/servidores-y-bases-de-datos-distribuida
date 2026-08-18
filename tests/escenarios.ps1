# Escenarios de prueba — Fase 2 (Windows).
#
# Escenario 1: operación normal (registro + replicación + consulta).
# Escenario 2: caída del Servidor 2, el Servidor 1 sigue atendiendo y,
#              al reactivarse, el Servidor 2 se resincroniza.
#
# Si la política de ejecución lo bloquea:
#   powershell -ExecutionPolicy Bypass -File .\tests\escenarios.ps1
#
# Al terminar, el despliegue queda activo para capturar evidencias;
# reviértalo con scripts\clean.ps1.

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Wait-For([int]$Seconds, [string]$Description) {
    Write-Host ""
    Write-Host ">>> Esperando $Seconds s ($Description)..."
    Start-Sleep -Seconds $Seconds
}

function Invoke-Client([string[]]$Args) {
    # --no-deps: el cliente no debe arrancar ni reiniciar servidores por su
    # cuenta (compose arranca las dependencias de `run`; eso arruinaría el
    # escenario de caída al "resucitar" al Servidor 2).
    docker compose run --rm --no-deps -T client python3 client.py @Args
    if ($LASTEXITCODE -ne 0) { Write-Host ">>> (el cliente terminó con código $LASTEXITCODE)" }
}

Write-Host "===== ESCENARIO 1: operación normal ====="
Write-Host ">>> Levantando bases de datos y servidores..."
docker compose up -d --build db1 db2 server1 server2
if ($LASTEXITCODE -ne 0) { throw "docker compose up falló" }
Wait-For 20 "arranque de PostgreSQL y de los servidores"

Write-Host ">>> Estado de los contenedores:"
docker compose ps

Write-Host ">>> 1.1 Crear un registro a través del Servidor 1:"
Invoke-Client @("create", "--payload", "Primer registro (vía servidor 1)", "--server", "1")

Write-Host ">>> 1.2 Consultarlo a través del Servidor 2 (evidencia de replicación):"
Invoke-Client @("list", "--server", "2")

Write-Host ">>> 1.3 Estado de ambos servidores y de su visión del par:"
Invoke-Client @("status")

Write-Host ""
Write-Host "===== ESCENARIO 2: caída y recuperación del Servidor 2 ====="
Write-Host ">>> 2.1 Deteniendo el Servidor 2..."
docker compose stop server2
Wait-For 8 "detección de la caída por el heartbeat"

Write-Host ">>> 2.2 Crear registros con el Servidor 2 caído:"
Write-Host ">>> (el primero pide server2 a propósito: el cliente debe conmutar a server1)"
Invoke-Client @("create", "--payload", "Registro creado con server2 caído (1)", "--server", "2")
Invoke-Client @("create", "--payload", "Registro creado con server2 caído (2)", "--server", "1")

Write-Host ">>> 2.3 El Servidor 1 sigue atendiendo con normalidad:"
Invoke-Client @("list", "--server", "1")
Invoke-Client @("status")

Write-Host ">>> 2.4 Reactivando el Servidor 2..."
docker compose start server2
Wait-For 25 "heartbeat, detección del par y resincronización"

Write-Host ">>> 2.5 El Servidor 2 ya tiene los registros creados durante su caída:"
Invoke-Client @("list", "--server", "2")

Write-Host ">>> 2.6 Estado final de los servidores:"
Invoke-Client @("status")

Write-Host ">>> 2.7 Historial local del cliente (SQLite):"
Invoke-Client @("history", "--limit", "15")

Write-Host ""
Write-Host ">>> Trazas del canal de sincronía (logs):"
docker compose logs server1 server2 | Select-String "\[sync\]" | Select-Object -Last 20

Write-Host ""
Write-Host "===== Escenarios terminados. ====="
Write-Host "El despliegue queda activo para las evidencias."
Write-Host "Para revertir: scripts\clean.ps1 (Windows) o scripts/clean.sh (Linux)."
