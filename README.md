# Guía #02 — Comunicación en Sistemas Distribuidos (Fase 2)

Sistema distribuido de **registro y consulta de información** con dos
servidores replicados (Debian y Fedora), un cliente (Ubuntu) y una base de
datos PostgreSQL independiente por servidor, todo orquestado con Docker
Compose sobre una red interna propia.

- Cliente ↔ servidores: **REST/HTTP** (Flask).
- Servidor ↔ servidor: **canal TCP propio** (JSON por línea) para heartbeat,
  replicación y resincronización.
- Tolerancia a fallos: si un servidor cae, el otro sigue atendiendo; al
  recuperarse, se resincroniza automáticamente.
- El cliente guarda un **historial local en SQLite** de sus comunicaciones.

Documentación de la Fase 1 (diseño): [docs/guia-02-sistemas-distribuidos-FASE-01.pdf](docs/guia-02-sistemas-distribuidos-FASE-01.pdf)

## Requisitos

Solo hace falta un motor de contenedores con Compose y Git:

- **Windows (ejecución oficial):** Docker Desktop 4.x con WSL2.
- **Linux (desarrollo):** Docker Engine + Compose, o Podman + podman-compose.

Todo lo demás (Python, Flask, PostgreSQL) corre dentro de los contenedores.

## Arranque rápido

```powershell
# Windows (PowerShell), desde la raíz del repositorio
docker compose up -d --build db1 db2 server1 server2   # ~20 s de espera
docker compose run --rm client                          # menú interactivo
```

En Linux los comandos son idénticos.

```powershell
# O en línea de comandos (para pruebas y evidencias):
docker compose run --rm --no-deps -T client python3 client.py create --payload "Hola mundo" --server 1
docker compose run --rm --no-deps -T client python3 client.py list --server 2
docker compose run --rm --no-deps -T client python3 client.py status
docker compose run --rm --no-deps -T client python3 client.py history
```

## Estructura del repositorio

| Ruta                                                 | Contenido                                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------ |
| [docker-compose.yml](docker-compose.yml)             | Servicios, red interna `sdnet`, IPs y puertos                                        |
| [server/](server/)                                   | API REST (Flask) + canal TCP de sincronía; mismo código para ambos servidores        |
| [server/Dockerfile.debian](server/Dockerfile.debian) | Imagen del Servidor 1 (Debian)                                                       |
| [server/Dockerfile.fedora](server/Dockerfile.fedora) | Imagen del Servidor 2 (Fedora)                                                       |
| [client/](client/)                                   | Cliente Ubuntu con historial local en SQLite                                         |
| [tests/](tests/)                                     | Escenarios de prueba (scripts + guía de resultados)                                  |
| [scripts/](scripts/)                                 | Limpieza/reversión del despliegue (`.ps1` y `.sh`)                                   |
| [docs/FASE-02/](docs/FASE-02/)                       | Manual, pruebas y resultados, notas técnicas, guion del video, diagramas, evidencias |

## Documentación de la Fase 2

| Documento                                                                                 | Qué contiene                                                                                   |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| [Manual de instalación y configuración](docs/FASE-02/manual-instalacion-configuracion.md) | **Entregable 4.** Runtime, dependencias, red, puertos, base de datos, ejecución y comunicación |
| [Pruebas y resultados](docs/FASE-02/pruebas-resultados.md)                                | **Entregables 5–7.** Escenarios, salidas esperadas, registro de resultados y capturas          |
| [Notas técnicas](docs/FASE-02/notas-tecnicas.md)                                          | Decisiones de diseño, protocolo TCP, esquema de BD, flujo Linux↔Windows                        |
| [Guion del video](docs/FASE-02/guion-video.md)                                            | Guía de grabación: funcionamiento normal y falla/recuperación                                  |
| [Diagramas PlantUML](docs/FASE-02/diagramas/)                                             | Fuentes `.puml` de despliegue y secuencias (renderizar con el plugin de PlantUML en VS Code)   |
| [Evidencias](docs/FASE-02/evidencias/)                                                    | Carpeta y convención para las capturas de pantalla                                             |

## Pruebas

```powershell
# Windows
.\tests\escenarios.ps1

# Linux
./tests/escenarios.sh
```

Cubren: operación normal (registro → replicación → consulta desde el otro
servidor) y caída del Servidor 2 con resincronización al recuperarse. Si
PowerShell bloquea el script: `powershell -ExecutionPolicy Bypass -File .\tests\escenarios.ps1`.

## Revertir el despliegue (sin dejar basura)

La aplicación solo crea contenedores, una red y volúmenes de Docker:

```powershell
.\scripts\clean.ps1            # Windows: contenedores + red + volúmenes
.\scripts\clean.ps1 -Images    # también elimina las imágenes construidas
```

```bash
./scripts/clean.sh             # Linux: contenedores + red + volúmenes
./scripts/clean.sh --images    # también elimina las imágenes construidas
```

Equivalente directo en ambos: `docker compose down -v --remove-orphans`.
Para conservar los datos entre sesiones use `docker compose stop` /
`docker compose start` en lugar de `down -v`.

## Flujo de trabajo del equipo

- El desarrollo ocurre en Linux y la ejecución/evidencias en Windows; el
  repositorio git es el canal de sincronización.
- `.gitattributes` fija los finales de línea (LF para shell/Python, CRLF
  para PowerShell) y `.gitignore` evita subir artefactos locales.
- Los datos de la aplicación viven solo en volúmenes de Docker: `git status`
  queda limpio tras cualquier prueba.
