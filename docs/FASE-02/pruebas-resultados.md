# Pruebas y resultados — Fase 2

Cubre los **entregables 5, 6 y 7** de `docs/instrucciones-adicionales.md`:
evidencias de ejecución en ambos servidores, evidencias de comunicación
entre servidores y resultados de las pruebas.

- [Ambiente de prueba](#ambiente-de-prueba)
- [Escenario 1 — Operación normal](#escenario-1--operación-normal)
- [Escenario 2 — Caída y recuperación del Servidor 2](#escenario-2--caída-y-recuperación-del-servidor-2)
- [Pruebas directas contra la API](#pruebas-directas-contra-la-api)
- [Evidencias de comunicación entre servidores](#evidencias-de-comunicación-entre-servidores)
- [Registro de resultados](#registro-de-resultados)
- [Lista de capturas de pantalla](#lista-de-capturas-de-pantalla)

---

## Ambiente de prueba

| Campo                       | Valor                                                               |
| --------------------------- | ------------------------------------------------------------------- |
| Fecha de ejecución          | _(por llenar)_                                                      |
| Equipo                      | _(por llenar)_                                                      |
| Sistema operativo anfitrión | Windows _(versión por llenar)_                                      |
| Docker                      | Docker Desktop _(versión por llenar)_ — `docker --version`          |
| Docker Compose              | _(versión por llenar)_ — `docker compose version`                   |
| Estado inicial              | Despliegue limpio: `.\scripts\clean.ps1` ejecutado antes de empezar |

Todos los comandos se ejecutan desde la **raíz del repositorio** en
PowerShell. Los escenarios pueden correrse completos con
`.\tests\escenarios.ps1` (Windows) o `./tests/escenarios.sh` (Linux); esta
guía muestra el mismo flujo paso a paso, con la salida esperada, para
capturar las evidencias.

> Las "salidas esperadas" son de referencia (capturadas en validación
> local). Los registros reales del equipo deben coincidir en estructura;
> los IDs UUID, marcas de tiempo y orden de algunos mensajes varían.

---

## Escenario 1 — Operación normal

**Objetivo:** registro vía Servidor 1, replicación inmediata al Servidor 2,
consulta desde el otro servidor, identificación del servidor que atiende y
estado de conexión de ambos.

### 1.0 Levantar el sistema

```powershell
docker compose up -d --build db1 db2 server1 server2
# esperar ~20 s
docker compose ps
```

**Esperado:** 4 contenedores en estado _running_/_healthy_: `sd2-db1`,
`sd2-db2`, `sd2-server1`, `sd2-server2`.

**Captura:** `ev-01-docker-compose-ps.png`

### 1.1 Evidencia de ejecución en ambos servidores (distribuciones)

```powershell
docker compose exec server1 sh -c "cat /etc/os-release | head -2"
docker compose exec server2 sh -c "cat /etc/os-release | head -2"
```

**Esperado:**

```
PRETTY_NAME="Debian GNU/Linux 13 (trixie)"     # server1
PRETTY_NAME="Fedora Linux 4x (…)"              # server2
```

**Captura:** `ev-02-distros.png`

### 1.2 Crear un registro a través del Servidor 1

```powershell
docker compose run --rm --no-deps -T client python3 client.py create --payload "Primer registro (vía servidor 1)" --server 1
```

**Esperado:**

```
Registro creado — atendido por server1
  id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  payload="Primer registro (vía servidor 1)"
```

**Captura:** `ev-03-create-server1.png`

### 1.3 Consultar el mismo registro desde el Servidor 2

```powershell
docker compose run --rm --no-deps -T client python3 client.py list --server 2
```

**Esperado:** la lista muestra el registro anterior con `origin=server1` y
la cabecera `atendido por server2`. **Esta es la evidencia de replicación
entre servidores.**

**Captura:** `ev-04-replicacion-s1-s2.png`

### 1.4 Estado de ambos servidores

```powershell
docker compose run --rm --no-deps -T client python3 client.py status
```

**Esperado:** ambos en línea, mismo número de registros, y cada uno "ve al
par en línea".

**Captura:** `ev-05-status-normal.png`

---

## Escenario 2 — Caída y recuperación del Servidor 2

**Objetivo:** con el Servidor 2 detenido, el Servidor 1 y el cliente siguen
funcionando; al reactivar el Servidor 2, este se resincroniza y recupera
los registros creados durante su caída.

### 2.1 Detener el Servidor 2

```powershell
docker compose stop server2
# esperar ~8 s (para que el heartbeat del server1 detecte la caída)
docker compose run --rm --no-deps -T client python3 client.py status
```

**Esperado:** `Servidor 2 (Fedora): NO RESPONDE` y el Servidor 1 reporta
"ve al par caído".

**Captura:** `ev-06-server2-caido.png`

### 2.2 Crear registros con el Servidor 2 caído

```powershell
docker compose run --rm --no-deps -T client python3 client.py create --payload "Registro creado con server2 caído (1)" --server 2
docker compose run --rm --no-deps -T client python3 client.py create --payload "Registro creado con server2 caído (2)" --server 1
```

**Esperado:** ambos responden `atendido por server1`. La primera petición
es la evidencia de la **conmutación por fallo del cliente**: se pidió el
Servidor 2 (caído) y el cliente intentó automáticamente con el Servidor 1.
Los registros quedan **pendientes** en el outbox del Servidor 1.

**Captura:** `ev-07-create-con-server2-caido.png`

### 2.3 El Servidor 1 sigue atendiendo con normalidad

```powershell
docker compose run --rm --no-deps -T client python3 client.py list --server 1
```

**Esperado:** lista completa atendida por `server1` (3 registros).

**Captura:** `ev-08-server1-normal-con-par-caido.png`

### 2.4 Reactivar el Servidor 2 y esperar la resincronización

```powershell
docker compose start server2
# esperar ~25 s (heartbeat + resincronización inicial + reintentos del outbox)
```

**Captura (opcional):** `docker compose ps` en este punto.

### 2.5 El Servidor 2 recuperó los registros de la caída

```powershell
docker compose run --rm --no-deps -T client python3 client.py list --server 2
```

**Esperado:** el Servidor 2 muestra **los 3 registros**, incluidos los dos
creados durante su caída. **Esta es la evidencia de la resincronización.**

**Captura:** `ev-09-resincronizacion-server2.png`

### 2.6 Estado final e historial del cliente

```powershell
docker compose run --rm --no-deps -T client python3 client.py status
docker compose run --rm --no-deps -T client python3 client.py history --limit 15
```

**Esperado:** ambos servidores en línea y con el mismo número de registros;
el historial SQLite muestra todas las comunicaciones (acción, servidor
objetivo, servidor que atendió, resultado).

**Captura:** `ev-10-status-final-historial.png`

---

## Pruebas directas contra la API

Sin pasar por el cliente (evidencia adicional de que ambos servidores
ejecutan su API):

```powershell
curl http://localhost:5000/api/status
curl http://localhost:5001/api/status
curl -X POST http://localhost:5000/api/records -H "Content-Type: application/json" -d '{"payload":"prueba directa curl"}'
curl "http://localhost:5001/api/records?limit=5"
```

**Captura:** `ev-11-curl-api.png`

---

## Evidencias de comunicación entre servidores

### Logs del canal de sincronía (marcados `[sync]`)

```powershell
docker compose logs server1 server2 | Select-String "\[sync\]" | Select-Object -Last 30
```

**Esperado (durante el Escenario 2):**

```
[sync] registro 62f3c1a8 replicado al par              # replicación normal (server1)
[sync] par no responde (caído o inalcanzable)          # detección de la caída
[sync] par inalcanzable; el registro 7b21… queda pendiente
[sync] replicación: 2 registro(s) pendiente(s) confirmados   # tras la recuperación
[sync] par recuperado; lanzando resincronización       # heartbeat detecta al par
[sync] resincronización completada: 2 registro(s) nuevos      # server2 (pull)
[sync] petición de resincronización: N registro(s), cursor=… # server1 (responde)
```

**Captura:** `ev-12-logs-sync.png`

### Verificación del canal TCP a nivel de red (opcional)

```powershell
docker compose exec server1 python3 ping_peer.py
docker compose exec server2 python3 ping_peer.py
```

**Esperado:** `{"type": "PONG", "server_id": "server2", "record_count": N}` (y
su equivalente desde server2 hacia server1). `ping_peer.py` está incluido
en la imagen de los servidores y usa las variables `PEER_HOST`/`PEER_PORT`.

**Captura:** `ev-13-ping-tcp.png`

---

## Registro de resultados

_(Completar tras ejecutar en el equipo; una fila por prueba.)_

| #   | Prueba                                | Resultado esperado                        | Resultado obtenido | ¿Cumple? |
| --- | ------------------------------------- | ----------------------------------------- | ------------------ | -------- |
| 1.1 | Ejecución server1 (Debian)            | `/etc/os-release` → Debian                |                    |          |
| 1.2 | Ejecución server2 (Fedora)            | `/etc/os-release` → Fedora                |                    |          |
| 1.3 | Crear registro vía server1            | 201, `served_by=server1`                  |                    |          |
| 1.4 | Consulta vía server2 tras replicación | El registro aparece, `served_by=server2`  |                    |          |
| 1.5 | Estado en operación normal            | Ambos en línea, par visible               |                    |          |
| 2.1 | Detección de la caída                 | `peer_online=false` y "NO RESPONDE"       |                    |          |
| 2.2 | Registro con server2 caído            | `served_by=server1`, pendiente en outbox  |                    |          |
| 2.3 | server1 sigue atendiendo              | Lista completa en server1                 |                    |          |
| 2.4 | Resincronización                      | server2 muestra los registros de la caída |                    |          |
| 2.5 | Estado final                          | Ambos en línea, mismos registros          |                    |          |
| 2.6 | Historial SQLite del cliente          | Trazas de todas las comunicaciones        |                    |          |
| 3.1 | Comunicación TCP entre servidores     | Logs `[sync]` + PONG directo              |                    |          |

---

## Lista de capturas de pantalla

Guardar en [evidencias/](evidencias/) (ver el README de esa carpeta):

| Archivo                                  | Contenido                                                |
| ---------------------------------------- | -------------------------------------------------------- |
| `ev-01-docker-compose-ps.png`            | `docker compose ps` con todo _healthy_                   |
| `ev-02-distros.png`                      | `/etc/os-release` de server1 (Debian) y server2 (Fedora) |
| `ev-03-create-server1.png`               | Registro creado vía Servidor 1                           |
| `ev-04-replicacion-s1-s2.png`            | Consulta vía Servidor 2 con el registro de server1       |
| `ev-05-status-normal.png`                | `client.py status` en operación normal                   |
| `ev-06-server2-caido.png`                | Estado con el Servidor 2 detenido                        |
| `ev-07-create-con-server2-caido.png`     | Registros creados durante la caída                       |
| `ev-08-server1-normal-con-par-caido.png` | Server1 atendiendo solo                                  |
| `ev-09-resincronizacion-server2.png`     | Server2 con los registros recuperados                    |
| `ev-10-status-final-historial.png`       | Estado final + historial SQLite                          |
| `ev-11-curl-api.png`                     | Pruebas directas con curl                                |
| `ev-12-logs-sync.png`                    | Logs `[sync]` de ambos servidores                        |
| `ev-13-ping-tcp.png`                     | PING/PONG directo por TCP (opcional)                     |
