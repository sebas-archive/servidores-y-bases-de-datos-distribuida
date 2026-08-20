# Comandos útiles

Referencia rápida de comandos para operar el proyecto de forma local con Docker Compose. No requieren conexión a ningún repositorio remoto.

## Servicios del proyecto

| Servicio | container_name | Rol | Puerto host |
|---|---|---|---|
| `db1` | sd2-db1 | PostgreSQL de server1 | interno |
| `db2` | sd2-db2 | PostgreSQL de server2 | interno |
| `server1` | sd2-server1 | API REST (Debian) | 5000 |
| `server2` | sd2-server2 | API REST (Fedora) | 5001 |
| `client` | sd2-client | Cliente CLI/interactivo | — |

## Arranque

```bash
docker compose up -d --build db1 db2 server1 server2
```
Levanta las bases de datos y los dos servidores (construye imágenes si hace falta).

```bash
docker compose up -d --build server1
```
Levanta/reconstruye solo el servidor 1 (igual con `server2`, `db1`, `db2`).

```bash
docker compose build
```
Solo construye las imágenes, sin arrancar nada.

```bash
docker compose build --no-cache
```
Reconstruye desde cero, ignorando la caché de Docker.

## Apagado individual (sin borrar datos)

```bash
docker compose stop server1
docker compose stop server2
docker compose stop db1
docker compose stop db2
docker compose stop server1 server2
```

## Encendido tras apagar

```bash
docker compose start server1
docker compose start server2
docker compose restart server1
```
`restart` apaga y vuelve a encender de una vez (igual con `server2`, `db1`, `db2`).

## Apagado total (sin borrar nada)

```bash
docker compose stop
```
Apaga todos los contenedores del proyecto, dejando volúmenes y red intactos.

## Limpieza — quitar contenedores (down)

```bash
docker compose down
```
Detiene y elimina contenedores + red, pero conserva los volúmenes (los datos de las bases persisten).

```bash
docker compose down --remove-orphans
```
Igual, y además elimina contenedores "huérfanos" que ya no están en el compose file.

```bash
docker compose down -v
```
Elimina contenedores, red **y volúmenes** (`db1_data`, `db2_data`, `client_history`) → borra todos los datos.

```bash
docker compose down -v --remove-orphans
```
Es lo que hace `scripts/clean.sh` por defecto.

```bash
docker compose down -v --remove-orphans --rmi local
```
Todo lo anterior + borra las imágenes construidas localmente (no las bajadas de Docker Hub, como `postgres:16`).

```bash
docker compose down -v --remove-orphans --rmi all
```
Igual, pero borra **todas** las imágenes usadas por el proyecto, incluida `postgres:16`.

## Scripts de limpieza del repo (equivalentes empaquetados)

```bash
./scripts/clean.sh
```
= `docker compose down -v --remove-orphans`

```bash
./scripts/clean.sh --images
```
= lo anterior + `--rmi local`

**Windows (PowerShell):**

```powershell
.\scripts\clean.ps1
.\scripts\clean.ps1 -Images
```

## Limpieza manual de volúmenes/red/imágenes puntuales

```bash
docker volume ls
```
Ver todos los volúmenes de Docker.

```bash
docker volume rm sd2_db1_data sd2_db2_data sd2_client_history
```
Borrar los volúmenes del proyecto uno por uno (el prefijo `sd2_` puede variar según el nombre de la carpeta del proyecto; confirma el nombre exacto con `docker volume ls`).

```bash
docker network rm sdnet
```
Borra la red del proyecto (solo si ya no hay contenedores conectados).

```bash
docker image prune -f
```
Borra imágenes "dangling" (sin tag, sobrantes de builds).

```bash
docker system prune -a --volumes
```
⚠️ Limpieza agresiva de **todo Docker** en la máquina (no solo este proyecto): contenedores parados, redes sin uso, imágenes sin uso y volúmenes sin uso. Confirma antes de ejecutarlo.

## Estado y logs

```bash
docker compose ps
docker compose ps -a
```
`-a` incluye contenedores detenidos.

```bash
docker compose top
```
Procesos corriendo dentro de cada contenedor.

```bash
docker stats
```
Uso de CPU/memoria en vivo de todos los contenedores.

```bash
docker compose logs -f server1
docker compose logs -f server2
```

```bash
docker compose logs server1 server2 | grep "\[sync\]" | tail -20
```
Últimos eventos de sincronización/replicación entre ambos servidores.

```bash
docker compose config
```
Valida y muestra el `docker-compose.yml` ya resuelto (útil para depurar variables de entorno).

## Entrar a un contenedor

```bash
docker compose exec server1 sh
```

```bash
docker compose exec db1 psql -U sduser -d records
```
Abre una sesión psql interactiva en la base del servidor 1.

## Cliente

```bash
docker compose run --rm client
```
Menú interactivo.

```bash
docker compose run --rm --no-deps -T client python3 client.py create --payload "Hola mundo" --server 1
docker compose run --rm --no-deps -T client python3 client.py list --server 2
docker compose run --rm --no-deps -T client python3 client.py status
docker compose run --rm --no-deps -T client python3 client.py history
```

## Pruebas

```bash
./tests/escenarios.sh
```

```powershell
.\tests\escenarios.ps1
```

## Prueba directa vía curl

```bash
curl http://localhost:5000/api/status
curl -X POST http://localhost:5001/api/records -H "Content-Type: application/json" -d '{"payload":"prueba curl"}'
```

## Resumen rápido de "nivel de borrado"

1. `docker compose stop` → solo pausa, no borra nada.
2. `docker compose down` → borra contenedores/red, conserva datos.
3. `docker compose down -v` → borra también los datos (bases y historial del cliente).
4. `./scripts/clean.sh --images` → borra todo lo anterior + imágenes construidas localmente.
5. `docker system prune -a --volumes` → borrado agresivo a nivel de todo Docker, no solo este proyecto.
