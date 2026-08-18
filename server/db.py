"""Acceso a la base de datos local de cada servidor (PostgreSQL).

Cada servidor administra su propia instancia de PostgreSQL (db1 o db2).
Este módulo contiene la creación del esquema y las consultas usadas por
la API REST y por el canal de replicación.

El esquema se crea con CREATE TABLE IF NOT EXISTS: al arrancar, el
servidor puede inicializar su base de datos sin herramientas externas.

Tablas:
  records  registros de la aplicación (idempotente por UUID)
  outbox   registros locales que aún no han sido confirmados por el par
"""

import time
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS records (
    id         UUID PRIMARY KEY,
    payload    TEXT NOT NULL,
    origin     VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outbox (
    record_id    UUID PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_attempt TIMESTAMPTZ
);
"""


def _to_json(row):
    """Convierte una fila de la base de datos en un dict serializable a JSON.

    psycopg devuelve las columnas uuid y timestamptz como objetos nativos
    (UUID, datetime); hay que pasarlos a string antes de enviarlos por la
    red o devolverlos en la API.
    """
    row = dict(row)
    created = row.get("created_at")
    if created is not None and hasattr(created, "isoformat"):
        row["created_at"] = created.isoformat()
    if isinstance(row.get("id"), uuid.UUID):
        row["id"] = str(row["id"])
    return row


class Database:
    """Envoltorio mínimo de psycopg: una conexión corta por operación."""

    def __init__(self, dsn, max_wait_seconds=120):
        self.dsn = dsn
        self.max_wait_seconds = max_wait_seconds

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    # --- arranque -------------------------------------------------------------

    def wait_until_ready(self):
        """Espera a que PostgreSQL acepte conexiones (arranque simultáneo)."""
        deadline = time.time() + self.max_wait_seconds
        while time.time() < deadline:
            try:
                with self._connect() as conn:
                    conn.execute("SELECT 1")
                return
            except psycopg.Error:
                time.sleep(2)
        raise RuntimeError(
            f"No se pudo conectar a PostgreSQL tras {self.max_wait_seconds}s"
        )

    def init_schema(self):
        with self._connect() as conn:
            conn.execute(SCHEMA_SQL)

    # --- registros ------------------------------------------------------------

    def insert_record(self, payload, origin):
        """Inserta un registro nuevo y lo deja pendiente de replicar (outbox).

        Devuelve el registro tal como quedó almacenado.
        """
        record = {
            "id": str(uuid.uuid4()),
            "payload": payload,
            "origin": origin,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO records (id, payload, origin, created_at) "
                "VALUES (%s, %s, %s, %s)",
                (record["id"], record["payload"], record["origin"], record["created_at"]),
            )
            conn.execute(
                "INSERT INTO outbox (record_id) VALUES (%s)",
                (record["id"],),
            )
        return record

    def upsert_record(self, record):
        """Inserta el registro si no existe (idempotente gracias al UUID).

        Devuelve True si el registro era nuevo en esta base, False si ya estaba.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO records (id, payload, origin, created_at) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (id) DO NOTHING",
                (record["id"], record["payload"], record["origin"], record["created_at"]),
            )
            return cur.rowcount > 0

    def list_records(self, limit=50):
        """Registros más recientes (para consulta del cliente)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, payload, origin, created_at FROM records "
                "ORDER BY created_at DESC, id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [_to_json(r) for r in rows]

    def count_records(self):
        with self._connect() as conn:
            return conn.execute("SELECT count(*) FROM records").fetchone()["count"]

    def records_after(self, cursor, batch=100):
        """Página de registros posteriores al cursor, en orden estable.

        El cursor es un dict {"created_at", "id"}; con None se obtiene la
        primera página. Usado por la resincronización.
        """
        if cursor is None:
            where = ""
            params = ()
        else:
            where = "WHERE (created_at, id) > (%s::timestamptz, %s::uuid)"
            params = (cursor["created_at"], cursor["id"])
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, payload, origin, created_at FROM records "
                f"{where} "
                f"ORDER BY created_at, id LIMIT %s",
                params + (batch,),
            ).fetchall()
        return [_to_json(r) for r in rows]

    # --- outbox (registros pendientes de replicar) -----------------------------

    def outbox_pending(self, limit=20):
        """Registros locales aún no confirmados por el servidor par."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.id, r.payload, r.origin, r.created_at "
                "FROM outbox o JOIN records r ON r.id = o.record_id "
                "ORDER BY o.record_id LIMIT %s",
                (limit,),
            ).fetchall()
        return [_to_json(r) for r in rows]

    def outbox_remove(self, record_id):
        """Elimina del outbox un registro ya confirmado por el par."""
        with self._connect() as conn:
            conn.execute("DELETE FROM outbox WHERE record_id = %s", (record_id,))

    def outbox_touch(self, record_id):
        """Registra un intento fallido de replicación."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE outbox SET attempts = attempts + 1, last_attempt = now() "
                "WHERE record_id = %s",
                (record_id,),
            )
