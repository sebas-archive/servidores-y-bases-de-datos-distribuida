# Evidencias — Fase 2

Esta carpeta recoge las capturas de pantalla de la ejecución en el equipo
(entregables 5, 6 y 7). El archivo
[pruebas-resultados.md](../pruebas-resultados.md) indica en qué paso del
escenario se toma cada captura y qué debe aparecer en ella.

## Convención de nombres

`ev-NN-descripcion-corta.png` — el número coincide con la lista de
[pruebas-resultados.md](../pruebas-resultados.md#lista-de-capturas-de-pantalla).

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

## Recomendaciones

- PNG a resolución completa de la ventana; que se lea el texto.
- Incluir en la captura el prompt de PowerShell con el comando ejecutado
  (la terminal completa, no solo la salida).
- Si una salida es larga (p. ej. el historial), una sola captura alcanza;
  no es necesario recortar.
- Subir las capturas al repositorio junto con el resto de la Fase 2.
