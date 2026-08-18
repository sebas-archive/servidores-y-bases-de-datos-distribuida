# Manual de instalación y configuración — Fase 2

Sistema distribuido de registro y consulta de información con dos servidores
replicados (Debian y Fedora), un cliente (Ubuntu) y una base de datos
PostgreSQL por servidor, todo orquestado con Docker Compose sobre una red
interna propia.

**Entregable 4 de la Fase 2** (ver `docs/instrucciones-adicionales.md`).

- [1. Requisitos previos](#1-requisitos-previos)
- [2. Instalación del lenguaje / runtime](#2-instalación-del-lenguaje--runtime)
- [3. Instalación de dependencias](#3-instalación-de-dependencias)
- [4. Configuración de red](#4-configuración-de-red)
- [5. Configuración de puertos](#5-configuración-de-puertos)
- [6. Instalación de la base de datos](#6-instalación-de-la-base-de-datos)
- [7. Ejecución del software](#7-ejecución-del-software)
- [8. Comunicación entre servidores](#8-comunicación-entre-servidores)
- [9. Reversión del despliegue (sin dejar basura)](#9-reversión-del-despliegue-sin-dejar-basura)
- [10. Solución de problemas](#10-solución-de-problemas)
- [Apéndice A. Configuración completa](#apéndice-a-configuración-completa)

---

## 1. Requisitos previos

| Componente            | Windows (ejecución)                      | Linux (desarrollo)                                 |
| --------------------- | ---------------------------------------- | -------------------------------------------------- |
| Motor de contenedores | Docker Desktop 4.x (con WSL2 habilitado) | Docker Engine + Compose, o Podman + podman-compose |
| Git                   | Sí (sincroniza el repo con el equipo)    | Sí                                                 |
| Puertos libres        | 5000 y 5001 en el anfitrión              | 5000 y 5001 en el anfitrión                        |

Todo el software de la aplicación (Python, Flask, PostgreSQL, SQLite) corre
**dentro de los contenedores**: no hay que instalar nada de eso en el
anfitrión. El anfitrión solo necesita Docker Compose y Git.

> En Windows conviene comprobar que Docker Desktop esté iniciado antes de
> ejecutar cualquier comando (`docker info` no debe dar error).

---

## 2. Instalación del lenguaje / runtime

El lenguaje es **Python 3**, instalado dentro de cada contenedor con el
gestor de paquetes propio de cada distribución base, tal como se definió en
la Fase 1:

| Contenedor | Imagen base     | Instalación de Python                 | Versión resultante |
| ---------- | --------------- | ------------------------------------- | ------------------ |
| Cliente    | `ubuntu:22.04`  | `apt-get install python3 python3-pip` | Python 3.10        |
| Servidor 1 | `debian:stable` | `apt-get install python3 python3-pip` | Python 3.13        |
| Servidor 2 | `fedora:latest` | `dnf install python3 python3-pip`     | Python 3.13/3.14   |

Las instrucciones exactas están en los Dockerfiles versionados:

- [client/Dockerfile](../../client/Dockerfile)
- [server/Dockerfile.debian](../../server/Dockerfile.debian)
- [server/Dockerfile.fedora](../../server/Dockerfile.fedora)

La instalación ocurre automáticamente durante `docker compose build`
(sección 7). No se ejecuta código Python en el anfitrión.

---

## 3. Instalación de dependencias

Dependencias de Python, declaradas en `requirements.txt` e instaladas con
`pip` en el momento del build de cada imagen:

| Componente | Dependencias           | Propósito                                         |
| ---------- | ---------------------- | ------------------------------------------------- |
| Servidores | `Flask>=3.0`           | API REST ligera en ambos servidores               |
| Servidores | `psycopg[binary]>=3.2` | Driver de PostgreSQL (conexión local a db1/db2)   |
| Cliente    | `requests>=2.31`       | Consumo de las API REST con conmutación por fallo |

Detalles por imagen:

- **Debian (servidor 1):** se usa `pip3 install --break-system-packages`
  porque Debian marca el Python del sistema como _externally managed_
  (PEP 668). Es seguro porque la instalación queda confinada al contenedor.
- **Fedora (servidor 2):** mismo comando; el flag es aceptado aunque Fedora
  no marque su Python como _externally managed_.
- **Ubuntu 22.04 (cliente):** `pip3 install` normal, sin flag.

---

## 4. Configuración de red

Docker Compose crea una **red interna bridge** llamada `sdnet` con el rango
`172.28.0.0/16` y asigna **direcciones IP fijas** a cada servicio (valores
definitivos de la Fase 2, pendientes en la Fase 1):

| Servicio                    | IP en `sdnet` | Nombre DNS interno |
| --------------------------- | ------------- | ------------------ |
| db1 (PostgreSQL de server1) | 172.28.0.11   | `db1`              |
| server1 (Debian)            | 172.28.0.21   | `server1`          |
| db2 (PostgreSQL de server2) | 172.28.0.12   | `db2`              |
| server2 (Fedora)            | 172.28.0.22   | `server2`          |
| client (Ubuntu)             | 172.28.0.30   | `client`           |

Reglas de comunicación:

- El cliente alcanza a los servidores por HTTP usando sus nombres DNS
  (`http://server1:5000`, `http://server2:5001`), no las IP: los nombres
  son más legibles y estables.
- Los servidores se alcanzan entre sí por el **canal TCP** usando también
  los nombres (`PEER_HOST`), puertos 6000/6001.
- La red `sdnet` es interna: nada de lo que ocurre dentro es visible desde
  el anfitrión salvo los puertos publicados (sección 5).

La definición completa está en [docker-compose.yml](../../docker-compose.yml).

---

## 5. Configuración de puertos

| Servicio | Puerto en contenedor | Publicado en anfitrión | Uso                                                  |
| -------- | -------------------- | ---------------------- | ---------------------------------------------------- |
| server1  | 5000 (Flask)         | `localhost:5000`       | API REST del Servidor 1                              |
| server1  | 6000 (TCP propio)    | —                      | Heartbeat, replicación y resincronización con el par |
| server2  | 5001 (Flask)         | `localhost:5001`       | API REST del Servidor 2                              |
| server2  | 6001 (TCP propio)    | —                      | Heartbeat, replicación y resincronización con el par |
| db1      | 5432 (PostgreSQL)    | —                      | Base local del Servidor 1                            |
| db2      | 5432 (PostgreSQL)    | —                      | Base local del Servidor 2                            |
| client   | —                    | —                      | Solo consumidor, no expone puertos                   |

Decisiones de diseño:

- **Solo 5000 y 5001 se publican** en el anfitrión: bastan para probar las
  API con curl o el navegador. Publicar menos puertos evita conflictos con
  otros servicios del equipo y simplifica la reversión.
- El canal TCP (6000/6001) y PostgreSQL (5432) viven únicamente en la red
  interna; su actividad se evidencia con los logs (sección 8).
- Si 5000 o 5001 estuvieran ocupados en el anfitrión, se cambia la parte
  izquierda del mapeo en `docker-compose.yml` (ej.: `"5100:5000"`) sin tocar
  nada dentro de los contenedores.

---

## 6. Instalación de la base de datos

Cada servidor administra su **propia instancia de PostgreSQL 16**
(imagen oficial, referenciada con su nombre completo
`docker.io/library/postgres:16` para que funcione tanto en Docker Desktop
como en podman), en contenedores separados:

| Parámetro        | db1        | db2        |
| ---------------- | ---------- | ---------- |
| Base de datos    | `records`  | `records`  |
| Usuario          | `sduser`   | `sduser`   |
| Contraseña       | `sdpass`   | `sdpass`   |
| Volumen de datos | `db1_data` | `db2_data` |

Notas:

- Los datos persisten en **volúmenes nombrados** de Docker, no en carpetas
  del repo: nada de lo que ejecute la aplicación ensucia el repositorio.
- El **esquema se crea automáticamente** al arrancar cada servidor
  (`CREATE TABLE IF NOT EXISTS` en `server/db.py`); no hay migraciones
  manuales ni archivos .sql que ejecutar.
- Tablas: `records` (registros, clave UUID) y `outbox` (registros locales
  aún no confirmados por el par). Detalle en las notas técnicas.

Verificación rápida dentro del contenedor (opcional, para evidencias):

```powershell
docker compose exec db1 psql -U sduser -d records -c "SELECT count(*) FROM records;"
```

---

## 7. Ejecución del software

### 7.1 Primer arranque

```powershell
# desde la raíz del repositorio
docker compose up -d --build db1 db2 server1 server2
```

Esto construye las imágenes (descarga las bases Debian/Fedora/PostgreSQL,
instala Python y dependencias) y levanta bases y servidores. La primera vez
tarda varios minutos por las descargas; luego es inmediato.

Esperar a que ambos servidores estén _healthy_ (también se puede lanzar
`docker compose ps` y revisar la columna STATUS):

```powershell
docker compose ps
```

### 7.2 Cliente — menú interactivo

```powershell
docker compose run --rm --no-deps client
```

Muestra el menú: crear registro, consultar registros, estado de los
servidores e historial local. Para salir, opción `0`. El contenedor se
elimina solo al salir (`--rm`).

> `--no-deps` evita que `docker compose run` arranque las dependencias del
> cliente (los servidores). Importante en los escenarios de falla: sin este
> flag, correr el cliente **reiniciaría** un servidor que se detuvo a
> propósito.

### 7.3 Cliente — línea de comandos (para pruebas y evidencias)

```powershell
# crear un registro (servidor preferido; conmuta solo si este no responde)
docker compose run --rm --no-deps -T client python3 client.py create --payload "Hola mundo" --server 1

# consultar registros desde el otro servidor
docker compose run --rm --no-deps -T client python3 client.py list --server 2

# estado de ambos servidores (incluye si cada uno ve a su par)
docker compose run --rm --no-deps -T client python3 client.py status

# historial local del cliente (SQLite)
docker compose run --rm --no-deps -T client python3 client.py history
```

### 7.4 Probar la API sin el cliente (opcional)

```powershell
curl http://localhost:5000/api/status
curl -X POST http://localhost:5001/api/records -H "Content-Type: application/json" -d '{"payload":"prueba curl"}'
```

### 7.5 Mismos pasos en Linux

Idénticos comandos; en shells bash el `-T` también funciona. Todo el flujo
es el mismo porque la aplicación vive en contenedores.

---

## 8. Comunicación entre servidores

Además del REST cliente↔servidor, los servidores mantienen un **canal TCP
propio** (6000 ↔ 6001) con tres funciones, tal como se diseñó en la Fase 1:

1. **Heartbeat (cada 5 s):** cada servidor envía `PING` al par; el par
   responde `PONG` con su estado. Así cada nodo sabe si el otro está vivo
   (visible en `client.py status`).
2. **Replicación por empuje:** al crear un registro, el servidor lo guarda
   en su base local y lo envía al par (`REPLICATE` → `ACK`). Si el par no
   responde, el registro queda en la tabla `outbox` y se reintenta cada 5 s.
3. **Resincronización (pull):** al arrancar, al detectar la recuperación
   del par y cada 60 s como red de seguridad, cada servidor pide los
   registros del par por páginas (`SYNC_REQUEST` → `SYNC_BATCH`) y los
   incorpora con UPSERT por UUID, que es idempotente.

Los mensajes son JSON, uno por línea, sobre TCP. Ver [notas-tecnicas.md](notas-tecnicas.md)
para el detalle del protocolo.

**Evidencia de la comunicación en los logs** (marcadas con `[sync]`):

```powershell
docker compose logs server1 server2 | Select-String "\[sync\]" | Select-Object -Last 30
```

---

## 9. Reversión del despliegue (sin dejar basura)

La aplicación solo crea: contenedores, una red y volúmenes de Docker. Nada
en el anfitrión fuera de eso. Para revertirlo todo:

### Windows

```powershell
.\scripts\clean.ps1            # contenedores + red + volúmenes
.\scripts\clean.ps1 -Images    # además, las imágenes construidas
```

Si la política de ejecución de PowerShell lo bloquea:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\clean.ps1
```

### Linux

```bash
./scripts/clean.sh            # contenedores + red + volúmenes
./scripts/clean.sh --images   # además, las imágenes construidas
```

### Equivalente directo (ambos sistemas)

```bash
docker compose down -v --remove-orphans      # y con --rmi local si se quieren borrar imágenes
```

El flag `-v` elimina los volúmenes (toda la data de db1/db2/historial), de
modo que el siguiente `up` parte de cero. Si se desea **conservar los
datos** entre sesiones, basta con `docker compose stop` / `docker compose
start` en lugar de `down -v`.

También es reversible el propio repositorio: cualquier cambio local se
deshace con `git restore .` y `git clean -fd` (¡cuidado: elimina archivos
sin seguimiento!).

---

## 10. Solución de problemas

| Síntoma                                                   | Causa probable                           | Solución                                                                                                                  |
| --------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `docker compose up` falla: puerto en uso                  | 5000/5001 ocupados en el anfitrión       | Cambiar el lado izquierdo del mapeo (sección 5) o liberar el puerto                                                       |
| El cliente dice "servidor X inalcanzable" justo tras `up` | Los servidores aún esperan a PostgreSQL  | Esperar ~15–20 s a que `docker compose ps` muestre _healthy_                                                              |
| `.ps1` bloqueado por política de ejecución                | Política _Restricted_ por defecto        | `powershell -ExecutionPolicy Bypass -File .\tests\escenarios.ps1` o `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Docker Desktop no arranca                                 | WSL2 sin habilitar / desactualizado      | `wsl --update` y reiniciar Docker Desktop                                                                                 |
| `docker compose down -v` da error de volumen en uso       | Algún contenedor sigue corriendo         | `docker compose down` primero; si no, `docker ps` y detener el contenedor                                                 |
| Imágenes enormes tras varias sesiones                     | Cache de builds acumulado                | `.\scripts\clean.ps1 -Images` (borra las locales)                                                                         |
| El build falla sin internet                               | Las imágenes base/pip requieren conexión | Revisar red; los paquetes se descargan una vez y quedan en cache                                                          |

---

## Apéndice A. Configuración completa

Variables de entorno de los servidores (valores por defecto en
`docker-compose.yml`):

| Variable             | server1                                       | server2                                       | Significado                                 |
| -------------------- | --------------------------------------------- | --------------------------------------------- | ------------------------------------------- |
| `SERVER_ID`          | `server1`                                     | `server2`                                     | Identidad del nodo (aparece en `served_by`) |
| `PORT`               | 5000                                          | 5001                                          | Puerto de la API REST                       |
| `SYNC_PORT`          | 6000                                          | 6001                                          | Puerto del canal TCP de sincronía           |
| `DB_DSN`             | `postgresql://sduser:sdpass@db1:5432/records` | `postgresql://sduser:sdpass@db2:5432/records` | Conexión a la base local                    |
| `PEER_HOST`          | `server2`                                     | `server1`                                     | Nombre DNS del par                          |
| `PEER_PORT`          | 6001                                          | 6000                                          | Puerto TCP del par                          |
| `HEARTBEAT_SECONDS`  | 5                                             | 5                                             | Intervalo del heartbeat                     |
| `REPLICATE_SECONDS`  | 5                                             | 5                                             | Intervalo de reintento del outbox           |
| `SYNC_EVERY_SECONDS` | 60                                            | 60                                            | Resincronización periódica de seguridad     |

Variables del cliente:

| Variable      | Valor                  | Significado                                             |
| ------------- | ---------------------- | ------------------------------------------------------- |
| `SERVER1_URL` | `http://server1:5000`  | Dirección del Servidor 1                                |
| `SERVER2_URL` | `http://server2:5001`  | Dirección del Servidor 2                                |
| `HISTORY_DB`  | `/app/data/history.db` | Archivo SQLite del historial (volumen `client_history`) |
