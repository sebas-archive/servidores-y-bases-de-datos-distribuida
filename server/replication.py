"""Canal TCP/IP entre servidores: heartbeat, replicación y resincronización.

Cada servidor ejecuta este módulo con su propia configuración (quién soy,
dónde está mi par). La comunicación usa mensajes JSON, uno por línea:

  PING         -> PONG        (heartbeat: el par responde con su estado)
  REPLICATE    -> ACK         (empuje de un registro local hacia el par)
  SYNC_REQUEST -> SYNC_BATCH  (resincronización paginada)

La convergencia entre bases se apoya en dos mecanismos redundantes:

  1. Empuje (push): todo registro creado localmente entra al "outbox" y se
     envía al par de inmediato; si el par no responde, se reintenta cada
     REPLICATE_SECONDS hasta recibir confirmación.
  2. Arrastre (pull): al arrancar, al detectar la recuperación del par y
     periódicamente (SYNC_EVERY_SECONDS), se piden los registros del par
     por páginas ordenadas.

Ambos caminos usan UPSERT por UUID, de modo que repetir un mensaje nunca
duplica datos: la replicación es idempotente.
"""

import json
import logging
import socket
import socketserver
import threading
import time

log = logging.getLogger("sync")

# Tipos de mensaje reconocidos por el protocolo
PING = "PING"
PONG = "PONG"
REPLICATE = "REPLICATE"
ACK = "ACK"
SYNC_REQUEST = "SYNC_REQUEST"
SYNC_BATCH = "SYNC_BATCH"


def send_tcp(host, port, messages, timeout=3):
    """Envía una lista de mensajes (dicts) y devuelve sus respuestas.

    Cada mensaje viaja en una línea JSON. Se espera exactamente una
    respuesta por mensaje; la conexión se cierra al terminar.
    """
    responses = []
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        reader = sock.makefile("rb")
        for msg in messages:
            sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        for _ in messages:
            line = reader.readline()
            if not line:
                break
            responses.append(json.loads(line.decode("utf-8")))
    return responses


class _Handler(socketserver.StreamRequestHandler):
    """Atiende una conexión TCP: lee mensajes y escribe una respuesta por cada uno."""

    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            reply = self.server.node.on_message(msg)
            if reply is not None:
                self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))
                self.wfile.flush()


class SyncNode:
    """Lado del protocolo TCP de un servidor: responde mensajes y mantiene
    los hilos de heartbeat, replicación y resincronización."""

    def __init__(self, server_id, db, peer_host, peer_port, sync_port,
                 heartbeat_seconds=5, replicate_seconds=5,
                 sync_every_seconds=60, sync_boot_delay=3,
                 sync_batch=100, request_timeout=3):
        self.server_id = server_id
        self.db = db
        self.peer_host = peer_host
        self.peer_port = peer_port
        self.sync_port = sync_port
        self.heartbeat_seconds = heartbeat_seconds
        self.replicate_seconds = replicate_seconds
        self.sync_every_seconds = sync_every_seconds
        self.sync_boot_delay = sync_boot_delay
        self.sync_batch = sync_batch
        self.request_timeout = request_timeout

        self.peer_online = False
        self.peer_record_count = None
        self.last_sync = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # --- arranque --------------------------------------------------------------

    def start(self):
        """Lanza los hilos: servidor TCP, heartbeat, outbox y resincronización inicial."""
        for target in (self._serve_tcp, self._heartbeat_loop, self._outbox_loop):
            threading.Thread(target=target, daemon=True, name=target.__name__).start()
        threading.Thread(target=self._initial_resync, daemon=True, name="initial-resync").start()

    def _serve_tcp(self):
        server = socketserver.ThreadingTCPServer(("0.0.0.0", self.sync_port), _Handler)
        server.daemon_threads = True
        server.node = self
        log.info("canal TCP escuchando en el puerto %s", self.sync_port)
        server.serve_forever()

    # --- manejo de mensajes entrantes (lado servidor) ---------------------------

    def on_message(self, msg):
        mtype = msg.get("type")
        if mtype == PING:
            return {
                "type": PONG,
                "server_id": self.server_id,
                "record_count": self.db.count_records(),
            }
        if mtype == REPLICATE:
            record = msg["record"]
            is_new = self.db.upsert_record(record)
            if is_new:
                log.info("registro %s recibido del par (nuevo)", record["id"][:8])
            return {"type": ACK, "record_id": record["id"]}
        if mtype == SYNC_REQUEST:
            cursor = msg.get("cursor")
            records = self.db.records_after(cursor, batch=self.sync_batch)
            log.info("petición de resincronización: %d registro(s), cursor=%s",
                     len(records), cursor)
            return {
                "type": SYNC_BATCH,
                "records": records,
                "has_more": len(records) == self.sync_batch,
            }
        return {"type": "ERROR", "detail": f"tipo de mensaje desconocido: {mtype!r}"}

    # --- heartbeat ---------------------------------------------------------------

    def _heartbeat_loop(self):
        while not self._stop.is_set():
            self._beat_once()
            self._stop.wait(self.heartbeat_seconds)

    def _beat_once(self):
        """Envía un PING al par y actualiza su estado. Si el par acaba de
        recuperarse, dispara la resincronización."""
        ok = False
        record_count = None
        try:
            replies = send_tcp(self.peer_host, self.peer_port,
                               [{"type": PING}], timeout=self.request_timeout)
            if replies and replies[0].get("type") == PONG:
                ok = True
                record_count = replies[0].get("record_count")
        except (OSError, json.JSONDecodeError):
            pass

        with self._lock:
            was_online = self.peer_online
            self.peer_online = ok
            self.peer_record_count = record_count

        if ok and not was_online:
            log.warning("par recuperado; lanzando resincronización")
            threading.Thread(target=self.safe_resync, daemon=True).start()
        elif not ok and was_online:
            log.warning("par no responde (caído o inalcanzable)")
        elif ok and time.time() - self.last_sync > self.sync_every_seconds:
            # sincronización periódica de seguridad
            threading.Thread(target=self.safe_resync, daemon=True).start()

    # --- replicación por empuje (outbox) ------------------------------------------

    def _outbox_loop(self):
        while not self._stop.is_set():
            try:
                self.flush_outbox()
            except Exception:
                log.exception("error en el ciclo de replicación")
            self._stop.wait(self.replicate_seconds)

    def flush_outbox(self):
        """Envía los registros pendientes y elimina los confirmados."""
        sent = 0
        for record in self.db.outbox_pending(limit=20):
            if self.push_record(record):
                sent += 1
        if sent:
            log.info("replicación: %d registro(s) pendiente(s) confirmados", sent)

    def push_record(self, record):
        """Intenta replicar un registro concreto; devuelve True si el par confirmó."""
        try:
            replies = send_tcp(self.peer_host, self.peer_port,
                               [{"type": REPLICATE, "record": record}],
                               timeout=self.request_timeout)
            if replies and replies[0].get("type") == ACK:
                self.db.outbox_remove(record["id"])
                log.info("registro %s replicado al par", record["id"][:8])
                return True
        except (OSError, json.JSONDecodeError):
            pass
        self.db.outbox_touch(record["id"])
        log.warning("par inalcanzable; el registro %s queda pendiente", record["id"][:8])
        return False

    # --- resincronización (pull paginado) ------------------------------------------

    def _initial_resync(self):
        self._stop.wait(self.sync_boot_delay)
        self.safe_resync()

    def safe_resync(self):
        """Resincroniza con el par; los errores quedan registrados, nunca tiran el hilo."""
        try:
            count = self.resync()
            self.last_sync = time.time()
            log.info("resincronización completada: %d registro(s) nuevos", count)
        except Exception:
            log.warning("resincronización no disponible (el par no responde)")

    def resync(self):
        """Pide al par todos sus registros por páginas y los incorpora.

        Devuelve cuántos registros nuevos se incorporaron en esta pasada.
        """
        cursor = None
        total = 0
        while True:
            replies = send_tcp(self.peer_host, self.peer_port,
                               [{"type": SYNC_REQUEST, "cursor": cursor}],
                               timeout=self.request_timeout)
            batch = replies[0]
            if batch.get("type") != SYNC_BATCH:
                raise RuntimeError(f"respuesta inesperada: {batch.get('type')}")
            records = batch.get("records", [])
            for record in records:
                if self.db.upsert_record(record):
                    total += 1
            if not batch.get("has_more") or not records:
                break
            last = records[-1]
            cursor = {"created_at": last["created_at"], "id": last["id"]}
        return total

    # --- estado para la API ---------------------------------------------------------

    def status(self):
        """Visión que tiene este servidor del par (para GET /api/status)."""
        with self._lock:
            return {
                "peer_online": self.peer_online,
                "peer_record_count": self.peer_record_count,
            }
