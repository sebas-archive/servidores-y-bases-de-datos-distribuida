# Guion del video explicativo — Fase 2

Video de demostración del sistema distribuido: funcionamiento normal y
escenario de falla y recuperación. Duración sugerida: **5–7 minutos**.

## Preparación previa (15 min antes de grabar)

1. Docker Desktop iniciado y estable.
2. Despliegue limpio: `.\scripts\clean.ps1` y luego
   `docker compose up -d --build db1 db2 server1 server2`.
3. Terminal con fuente grande (Ctrl + / —), ventana maximizada.
4. Verificar con `docker compose ps` que los 4 contenedores estén _healthy_.
5. Opcional: abrir el diagrama `docs/FASE-02/diagramas/despliegue.puml`
   renderizado para mostrarlo en pantalla durante la introducción.

## Sección 1 — Introducción (0:00 – 1:00)

**Qué mostrar:** el diagrama de arquitectura o el `docker-compose.yml`.

**Qué decir:**

> Este es el sistema distribuido de registro y consulta de información de
> la guía 2. Tenemos un cliente Ubuntu, dos servidores —uno Debian y uno
> Fedora— y una base de datos PostgreSQL independiente por servidor, todo
> orquestado con Docker Compose sobre una red interna con direcciones IP
> fijas. El cliente habla con los servidores por REST/HTTP, y los servidores
> se comunican entre sí por un canal TCP propio en los puertos 6000 y 6001:
> heartbeat cada 5 segundos, replicación de registros y resincronización.
> Cada respuesta indica qué servidor atendió la solicitud.

## Sección 2 — Operación normal (1:00 – 3:00)

**Comandos a ejecutar en orden** (leer el resultado en voz alta):

```powershell
docker compose ps

docker compose run --rm --no-deps -T client python3 client.py create --payload "Registro de demostración" --server 1

docker compose run --rm --no-deps -T client python3 client.py list --server 2

docker compose run --rm --no-deps -T client python3 client.py status
```

**Qué decir (guía):**

> El registro se crea a través del Servidor 1: la respuesta dice que lo
> atendió server1. Ahora lo consulto desde el Servidor 2: aparece el mismo
> registro, con su origen server1, y la respuesta dice que lo atendió
> server2. Esto evidencia que la replicación entre los dos servidores
> funciona: el Servidor 1 guardó en su PostgreSQL local y replicó al
> Servidor 2 por el canal TCP. El estado muestra ambos servidores en línea,
> con el mismo número de registros, y cada uno ve a su par.

## Sección 3 — Falla y recuperación (3:00 – 5:30)

**Comandos a ejecutar en orden:**

```powershell
docker compose stop server2
# ~8 segundos de espera
docker compose run --rm --no-deps -T client python3 client.py status

docker compose run --rm --no-deps -T client python3 client.py create --payload "Registro con server2 caído" --server 2

docker compose run --rm --no-deps -T client python3 client.py list --server 1

docker compose start server2
# ~25 segundos de espera
docker compose run --rm --no-deps -T client python3 client.py list --server 2

docker compose run --rm --no-deps -T client python3 client.py status
```

**Qué decir (guía):**

> Ahora detengo el Servidor 2 para simular una caída. El estado muestra que
> el Servidor 2 no responde y que el Servidor 1 lo marca como caído por el
> heartbeat. Creo un registro pidiendo el Servidor 2: fíjense que el cliente
> conmuta automáticamente y lo atiende el Servidor 1 — el sistema sigue
> funcionando con un nodo caído. El registro queda pendiente de replicar en
> la base local del Servidor 1.
>
> Reactivo el Servidor 2. Al volver, ejecuta su resincronización: pide al
> Servidor 1 los registros que le faltan. La consulta ahora muestra en el
> Servidor 2 el registro que se creó durante su caída. Ambos vuelven a
> quedar consistentes: los dos con los mismos datos.

**Opcional (si hay tiempo):** mostrar los logs de sincronía:

```powershell
docker compose logs server1 server2 | Select-String "\[sync\]" | Select-Object -Last 20
```

> Acá se ve el rastro del canal TCP: el par marcado como caído, los
> registros pendientes, la resincronización completada y el par recuperado.

## Sección 4 — Cierre (5:30 – 6:30)

**Qué mostrar:** el historial local del cliente y el repo.

```powershell
docker compose run --rm --no-deps -T client python3 client.py history --limit 15
```

**Qué decir:**

> Por último, el historial local del cliente en SQLite: cada comunicación
> quedó registrada —a qué servidor se pidió, cuál atendió y el resultado—,
> sin duplicar los datos de los servidores. Todo el código fuente, el
> docker-compose, el manual de instalación y las pruebas están versionados
> en el repositorio de GitHub del equipo.

## Cierre de la grabación

Al terminar: `.\scripts\clean.ps1` (deja el equipo listo para la próxima
sesión) y subir el video al medio indicado por el docente.
