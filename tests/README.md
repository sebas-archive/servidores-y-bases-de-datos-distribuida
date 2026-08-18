# Pruebas — Fase 2

Los escenarios de prueba cubren los dos casos exigidos por la guía:

| Escenario               | Qué demuestra                                                                                                                                                                    |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Operación normal     | Registro vía Servidor 1, replicación al Servidor 2, consulta desde el otro servidor, identificación del servidor que atiende y estado de conexión de ambos.                      |
| 2. Caída y recuperación | Con el Servidor 2 detenido, el Servidor 1 (y el cliente) siguen funcionando; al reactivar el Servidor 2, este se resincroniza y recupera los registros creados durante su caída. |

## Ejecución automatizada

- Windows (PowerShell): `.\tests\escenarios.ps1`
- Linux (bash): `./tests/escenarios.sh`

> En Windows, si la política de ejecución bloquea el script:
> `powershell -ExecutionPolicy Bypass -File .\tests\escenarios.ps1`

## Ejecución manual

Los mismos pasos, comando por comando, están en
[pruebas-resultados.md](../docs/FASE-02/pruebas-resultados.md), junto con las
salidas esperadas y la plantilla para registrar los resultados.

## Tiempos

El heartbeat y la replicación corren cada 5 segundos y la resincronización
inicial espera 3 segundos tras el arranque. Por eso los escenarios incluyen
pausas de 20–25 segundos tras levantar o reactivar servidores; no las reduzca
a menos que ajuste `HEARTBEAT_SECONDS` / `REPLICATE_SECONDS` en
`docker-compose.yml`.

## Limpieza

Al terminar, el despliegue queda activo a propósito (para capturar evidencias).
Para revertirlo por completo:

- Windows: `.\scripts\clean.ps1` (con `-Images` también borra las imágenes construidas)
- Linux: `./scripts/clean.sh` (con `--images` también borra las imágenes construidas)
