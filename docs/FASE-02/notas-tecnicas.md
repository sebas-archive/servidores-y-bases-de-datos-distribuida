# Notas técnicas y decisiones de diseño — Fase 2

Documento de contexto para el equipo: registra las decisiones tomadas al
implementar la Fase 2, el detalle del protocolo entre servidores y el flujo
de trabajo entre las dos máquinas. No es un entregable de la actividad, es
el "por qué" detrás del código.

- [Decisiones de diseño](#decisiones-de-diseño)
- [Protocolo TCP entre servidores](#protocolo-tcp-entre-servidores)
- [Esquema de la base de datos](#esquema-de-la-base-de-datos)
- [Cómo converge el sistema](#cómo-converge-el-sistema)
- [Flujo de trabajo Linux ↔ Windows](#flujo-de-trabajo-linux--windows)
- [Límites conocidos](#límites-conocidos)
- [Bitácora de cambios](#bitácora-de-cambios)

---

## Decisiones de diseño

### Un solo código de servidor, dos imágenes distintas

Ambos servidores ejecutan exactamente el mismo código (`server/`); lo único
que cambia es el Dockerfile (apt en Debian, dnf en Fedora) y las variables
de entorno de `docker-compose.yml` (`SERVER_ID`, `PORT`, `DB_DSN`,
`PEER_*`). Ventajas: un solo lugar donde corregir errores, y se cumple lo
prometido en la Fase 1: "los 2 servidores se comportan como réplicas" con
la diferencia real en la distribución base y su gestor de paquetes.

### Flask, no FastAPI

La Fase 1 dejó abierto "Flask y/o FastAPI". Se eligió **Flask**: es
suficiente para estos endpoints, tiene menos superficie de configuración y
el código queda más corto y legible. Los puertos quedan 5000/5001, tal como
aparecía en la columna Flask de la tabla de la Fase 1. FastAPI no aporta
nada aquí: no se necesitan validaciones automáticas de esquema ni async.

### Canal TCP propio (no HTTP) para servidor↔servidor

La Fase 1 especificaba "REST sobre HTTP para cliente-servidor, y TCP/IP
para heartbeat y replicación de estado". Para honrarlo (y de paso mostrar
un protocolo de aplicación sobre sockets crudos), la comunicación entre
servidores es un **protocolo JSON-lines sobre TCP** en los puertos
6000/6001: mensajes JSON de una línea, una respuesta por mensaje, conexión
corta por intercambio. Implementación: `socketserver.ThreadingTCPServer`
(~150 líneas con comentarios).

### Outbox: no perder escrituras si el par está caído

Al recibir un `POST /api/records`, el servidor:

1. Guarda en su base local (con commit).
2. Lo inserta en la tabla `outbox` (marca de "pendiente de replicar").
3. Intenta el `REPLICATE` inmediato; si el par confirma, borra la entrada
   del outbox.
4. Si no confirma, un hilo reintenta cada 5 s hasta lograrlo.

Así, ninguna escritura se pierde por una falla de red: el cambio ya está
persistido localmente y solo espera confirmación del par. Es el mismo
patrón _transactional outbox_ que usan los sistemas de mensajería reales,
en versión mínima.

### Idempotencia por UUID: la clave de la convergencia

Cada registro nace con un UUID generado por el servidor de origen y se
incorpora siempre con `INSERT ... ON CONFLICT (id) DO NOTHING`. Por eso da
igual que un registro llegue dos veces (por el empuje y por la
resincronización a la vez): nunca se duplica. Esta propiedad es la que
permite que los dos mecanismos de sincronía (push y pull) convivan sin
coordinación adicional.

### Resincronización paginada con cursor (created_at, id)

El pull usa páginas de 100 registros ordenadas por `(created_at, id)`. El
cursor es la última pareja recibida; la siguiente página pide los registros
posteriores. El orden es estable gracias al desempate por UUID y las
comparaciones usan cast explícito (`%s::timestamptz, %s::uuid`). Los
registros que lleguen "tarde" (fuera del orden del cursor) no se pierden:
el canal de empuje los entrega igualmente.

### Tres disparadores de sincronización

1. **Arranque:** cada servidor resincroniza ~3 s después de iniciar.
2. **Recuperación del par:** el heartbeat (5 s) detecta la transición
   caído→vivo y lanza la resincronización.
3. **Periódica (60 s):** red de seguridad que corrige cualquier hueco.

---

## Protocolo TCP entre servidores

Formato: **JSON, un mensaje por línea** (`json.dumps + "\n"`). El cliente
abre una conexión, envía sus mensajes y lee exactamente una respuesta por
mensaje; luego cierra. Timeout de 3 s por operación.

| Mensaje        | Quién lo envía                    | Cuerpo                                        | Respuesta                          |
| -------------- | --------------------------------- | --------------------------------------------- | ---------------------------------- |
| `PING`         | cualquiera (heartbeat)            | `{}`                                          | `PONG {server_id, record_count}`   |
| `REPLICATE`    | servidor con registro pendiente   | `{record: {id, payload, origin, created_at}}` | `ACK {record_id}`                  |
| `SYNC_REQUEST` | servidor que quiere sincronizarse | `{cursor: {created_at, id} \| null}`          | `SYNC_BATCH {records[], has_more}` |
| `ERROR`        | cualquiera                        | `{detail}`                                    | — (respuesta)                      |

Ejemplo de intercambio real (heartbeat):

```
→ {"type": "PING"}
← {"type": "PONG", "server_id": "server2", "record_count": 7}
```

Reglas:

- Los mensajes entrantes se responden en el mismo orden en que llegan.
- Un `REPLICATE` recibido **no se re-envía** al par: solo los registros con
  `origin == SERVER_ID` propio entran al outbox. Esto evita bucles
  ping-pong entre los dos nodos.
- Los logs del canal usan el prefijo `[sync]` para poder filtrarlos con
  `docker compose logs`.

---

## Esquema de la base de datos

Cada servidor tiene su propia base `records` en su PostgreSQL:

```sql
CREATE TABLE IF NOT EXISTS records (
    id         UUID PRIMARY KEY,
    payload    TEXT NOT NULL,
    origin     VARCHAR(32) NOT NULL,      -- qué servidor creó el registro
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbox (
    record_id    UUID PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_attempt TIMESTAMPTZ
);
```

- `origin` es informativo y a la vez funcional (decide qué entra al outbox).
- `outbox` solo existe en el servidor que originó cada registro.
- El esquema se crea al arrancar (`init_schema`), sin migraciones.

El cliente usa SQLite (`client_history` → `/app/data/history.db`) con una
única tabla `history` (ts, action, target, served_by, result, detail):
registra **qué pasó con cada comunicación**, sin copiar los datos de los
servidores, como pedía la Fase 1.

---

## Cómo converge el sistema

- **Camino feliz:** POST en server1 → INSERT local → REPLICATE a server2 →
  UPSERT en db2 → ACK → outbox limpio. Latencia de replicación: la del
  round-trip TCP interno (< 5 ms).
- **Par caído:** el registro queda en outbox y se reintenta cada 5 s;
  mientras tanto server1 atiende con normalidad.
- **Par recuperado:** tres caminos redundantes actúan a la vez
  (resincronización inicial del nodo recuperado, resincronización
  disparada por el heartbeat del nodo sano, reintentos del outbox). Gracias
  al UPSERT idempotente no importa que se solapen.
- **Ambos caídos y uno vuelve:** el que vuelve primero espera al otro en su
  heartbeat; al volver el segundo, cualquiera de los dos detecta la
  transición y sincroniza.

---

## Flujo de trabajo Linux ↔ Windows

- El desarrollo ocurre en Linux (Arch + podman); la ejecución y las
  evidencias oficiales, en Windows (Docker Desktop). El repositorio es el
  canal de sincronización.
- `.gitattributes` fija los finales de línea (`LF` para .sh/.py/.md, `CRLF`
  para .ps1) para que git los convierta automáticamente en cada checkout.
- En el equipo Linux de desarrollo no hay Docker real: el comando `docker`
  está emulado por **podman** (`podman-compose`). El archivo
  `docker-compose.yml` evita características que solo soporta Docker
  Compose moderno (como `depends_on.condition: service_healthy`) para
  funcionar igual en ambos; la espera por la base de datos la hace el
  propio código (`wait_until_ready`, con reintentos de 2 s durante 120 s).
- La aplicación **nunca** escribe fuera de contenedores y volúmenes de
  Docker: el repo queda limpio con `git status` tras cualquier prueba.
- Trampa conocida: `docker compose run` arranca las dependencias del
  servicio. Por eso los escenarios de caída usan `--no-deps` en cada
  invocación del cliente: sin ese flag, correr el cliente "resucitaría" al
  servidor detenido a propósito (comportamiento verificado en podman; Docker
  Compose hace lo mismo).
- Reversión: `docker compose down -v` (o los scripts `scripts/clean.*`)
  elimina contenedores, red y volúmenes. Para datos persistentes entre
  sesiones usar `stop`/`start` en vez de `down -v`.

---

## Límites conocidos

- **Consistencia eventual:** entre una escritura y su réplica hay ventanas
  de segundos (o de minutos si el par está caído). No hay consenso
  distribuido ni transacciones entre nodos: el objetivo de la actividad es
  replicación con tolerancia a fallos, no consistencia fuerte.
- **Sin resolución de conflictos:** los registros son de solo creación
  (nunca se editan ni borran), por lo que no existen conflictos de
  escritura concurrente.
- **Relojes:** los dos contenedores comparten el reloj del anfitrión
  (Docker), así que los `created_at` son comparables en la práctica. Si
  cada nodo corriera en máquinas físicas distintas habría que revisar la
  estrategia de cursor por reloj (NTP o un contador lógico).
- **Partición de red no simulada:** detener un contenedor corta todas las
  rutas hacia él; no se simulan fallos parciales de red.
- **Escala:** el pull envía páginas de 100 registros y el historial del
  cliente crece sin límite; pensado para el volumen de una demostración.

---

## Bitácora de cambios

| Fecha      | Cambio                                                                                                                                                                                                   |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-08-17 | Fase 2: implementación completa (servidores Flask + PostgreSQL, canal TCP de sincronía, cliente con historial SQLite, docker-compose con red e IPs fijas, scripts de prueba y reversión, documentación). |
| 2026-08-17 | Corrección en Windows: `tests/escenarios.ps1` reescrito con comandos literales (sin splatting de `$Args` ni acentos) porque en PowerShell 5.1 las invocaciones automatizadas del cliente abrían el menú interactivo en lugar de ejecutar el subcomando. Además, `client.py` ya no abre el menú cuando stdin no es una terminal (defensa adicional para corridas automatizadas). |
| 2026-08-18 | Informe de entrega: `docs/FASE-02/Informe-Fase-2-Sistemas-Distribuidos.docx` generado con `tools/generar-informe-fase2.py` (python-docx, estilo APA 7 simple). Incluye requerimientos funcionales/no funcionales, declaraciones de uso de herramientas de IA al inicio y al final, y 16 figuras con etiquetas `[IMAGEN: ...]` para que el equipo inserte las capturas. |
