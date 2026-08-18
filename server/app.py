"""API REST del servidor de registros — Fase 2, Sistemas Distribuidos.

El mismo código se despliega en el Servidor 1 (Debian) y en el Servidor 2
(Fedora); toda la configuración llega por variables de entorno definidas
en docker-compose.yml.

Endpoints:
  GET  /api/health    comprobación de vida (healthcheck de Docker)
  GET  /api/status    estado propio y visión del servidor par
  GET  /api/records   registros almacenados (parámetro opcional: limit)
  POST /api/records   crea un registro y lo replica al par   {"payload": "..."}

Toda respuesta incluye "served_by" para identificar qué servidor atendió
la solicitud.
"""

import logging
import os

from flask import Flask, jsonify, request

from db import Database
from replication import SyncNode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("api")

# --- configuración (ver docker-compose.yml) ----------------------------------

SERVER_ID = os.environ["SERVER_ID"]
PORT = int(os.environ.get("PORT", "5000"))
SYNC_PORT = int(os.environ.get("SYNC_PORT", "6000"))
DB_DSN = os.environ["DB_DSN"]
PEER_HOST = os.environ["PEER_HOST"]
PEER_PORT = int(os.environ.get("PEER_PORT", "6000"))

HEARTBEAT_SECONDS = int(os.environ.get("HEARTBEAT_SECONDS", "5"))
REPLICATE_SECONDS = int(os.environ.get("REPLICATE_SECONDS", "5"))
SYNC_EVERY_SECONDS = int(os.environ.get("SYNC_EVERY_SECONDS", "60"))

MAX_PAYLOAD_CHARS = 500

# --- arranque ----------------------------------------------------------------

db = Database(DB_DSN)
db.wait_until_ready()
db.init_schema()

node = SyncNode(
    server_id=SERVER_ID,
    db=db,
    peer_host=PEER_HOST,
    peer_port=PEER_PORT,
    sync_port=SYNC_PORT,
    heartbeat_seconds=HEARTBEAT_SECONDS,
    replicate_seconds=REPLICATE_SECONDS,
    sync_every_seconds=SYNC_EVERY_SECONDS,
)
node.start()

app = Flask(__name__)


# --- endpoints ---------------------------------------------------------------

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "server_id": SERVER_ID})


@app.get("/api/status")
def status():
    return jsonify({
        "server_id": SERVER_ID,
        "record_count": db.count_records(),
        "peer": node.status(),
    })


@app.get("/api/records")
def list_records():
    limit = min(int(request.args.get("limit", "50")), 200)
    records = db.list_records(limit=limit)
    return jsonify({
        "served_by": SERVER_ID,
        "count": len(records),
        "records": records,
    })


@app.post("/api/records")
def create_record():
    body = request.get_json(silent=True) or {}
    payload = (body.get("payload") or "").strip()
    if not payload:
        return jsonify({"error": "el campo 'payload' es obligatorio"}), 400
    if len(payload) > MAX_PAYLOAD_CHARS:
        return jsonify({"error": f"'payload' no puede superar {MAX_PAYLOAD_CHARS} caracteres"}), 400

    # 1) se guarda primero en la base local, 2) luego se replica al par;
    # si el par no responde, el registro queda pendiente en el outbox.
    record = db.insert_record(payload, origin=SERVER_ID)
    node.push_record(record)

    log.info("registro %s creado por %s: %r", record["id"][:8], SERVER_ID, payload)
    return jsonify({"served_by": SERVER_ID, "record": record}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
