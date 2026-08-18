"""Cliente de la aplicación (contenedor Ubuntu 22.04).

Consume la API REST de los dos servidores y conserva un historial local
en SQLite: a qué servidor se conectó, cuándo y qué ocurrió (sin duplicar
los datos completos que viven en los servidores).

Uso:
  python3 client.py                                -> menú interactivo
  python3 client.py create --payload "texto" [--server 1|2|auto]
  python3 client.py list   [--server 1|2|auto] [--limit 20]
  python3 client.py status
  python3 client.py history [--limit 20]

Conmutación por fallo: si el servidor preferido no responde, el cliente
intenta automáticamente con el otro y lo deja registrado en el historial.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone

import requests

SERVER1_URL = os.environ.get("SERVER1_URL", "http://server1:5000")
SERVER2_URL = os.environ.get("SERVER2_URL", "http://server2:5001")
HISTORY_DB = os.environ.get("HISTORY_DB", "/app/data/history.db")
TIMEOUT_SECONDS = 3

SERVERS = {"1": SERVER1_URL, "2": SERVER2_URL}


# --- historial local (SQLite) ---------------------------------------------------

def _history_conn():
    os.makedirs(os.path.dirname(HISTORY_DB), exist_ok=True)
    conn = sqlite3.connect(HISTORY_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT NOT NULL,
            action    TEXT NOT NULL,
            target    TEXT NOT NULL,
            served_by TEXT,
            result    TEXT NOT NULL,
            detail    TEXT
        )
        """
    )
    return conn


def history_log(action, target, result, served_by=None, detail=""):
    """Registra una comunicación del cliente en el historial local."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _history_conn() as conn:
        conn.execute(
            "INSERT INTO history (ts, action, target, served_by, result, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, action, target, served_by, result, detail),
        )


def history_show(limit=20):
    with _history_conn() as conn:
        rows = conn.execute(
            "SELECT ts, action, target, served_by, result, detail "
            "FROM history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        print("(historial vacío)")
        return
    print(f"{'CUÁNDO (UTC)':21} {'ACCIÓN':8} {'OBJETIVO':10} {'ATENDIÓ':10} {'RESULTADO':9} DETALLE")
    for ts, action, target, served_by, result, detail in rows:
        print(f"{ts:21} {action:8} {target:10} {served_by or '-':10} {result:9} {detail or ''}")


# --- peticiones HTTP con conmutación por fallo ------------------------------------

def http_request(method, path, server_choice="auto", payload=None, failover=True):
    """Llama al servidor elegido; si no responde, intenta con el otro.

    Devuelve (json_de_respuesta, url_usada). Lanza RuntimeError si ningún
    servidor respondió. Con failover=False solo se intenta el servidor pedido.
    """
    order = ["1", "2"] if server_choice == "auto" else [server_choice]
    if failover:
        order += [s for s in ("1", "2") if s not in order]

    last_error = None
    for key in order:
        url = f"{SERVERS[key]}{path}"
        try:
            resp = requests.request(method, url, json=payload, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json(), url
        except (requests.ConnectionError, requests.Timeout):
            last_error = f"servidor {key} inalcanzable"
            continue
        except requests.HTTPError as exc:
            # el servidor respondió con un error de negocio: no hay que conmutar
            return exc.response.json(), url
    raise RuntimeError(last_error or "sin servidores disponibles")


# --- comandos ----------------------------------------------------------------------

def cmd_create(args):
    try:
        data, _ = http_request("POST", "/api/records", args.server, {"payload": args.payload})
    except RuntimeError as exc:
        history_log("create", args.server, "error", detail=str(exc))
        print(f"ERROR: {exc}")
        return 1
    served = data["served_by"]
    record = data["record"]
    history_log("create", args.server, "ok", served_by=served, detail=record["id"][:8])
    print(f"Registro creado — atendido por {served}")
    print(f"  id={record['id']}")
    print(f"  payload=\"{record['payload']}\"")
    return 0


def cmd_list(args):
    try:
        data, _ = http_request("GET", f"/api/records?limit={args.limit}", args.server)
    except RuntimeError as exc:
        history_log("list", args.server, "error", detail=str(exc))
        print(f"ERROR: {exc}")
        return 1
    served = data["served_by"]
    history_log("list", args.server, "ok", served_by=served,
                detail=f"{data['count']} registro(s)")
    print(f"Registros almacenados — atendido por {served} ({data['count']} mostrados):")
    for r in data["records"]:
        print(f"  [{r['created_at']}] ({r['origin']}) {r['id'][:8]} — {r['payload']}")
    return 0


def cmd_status(args):
    for key, label in (("1", "Servidor 1 (Debian) "), ("2", "Servidor 2 (Fedora)")):
        try:
            data, _ = http_request("GET", "/api/status", key, failover=False)
            peer = data["peer"]
            peer_state = "en línea" if peer["peer_online"] else "caído"
            print(f"{label} [{data['server_id']}]: en línea, {data['record_count']} registro(s), "
                  f"ve al par {peer_state}")
            history_log("status", key, "ok", served_by=data["server_id"])
        except RuntimeError as exc:
            print(f"{label}: NO RESPONDE")
            history_log("status", key, "error", detail=str(exc))
    return 0


def cmd_history(args):
    history_show(args.limit)
    return 0


# --- menú interactivo ----------------------------------------------------------------

MENU = """
  ==== Cliente — Sistema distribuido de registros (Fase 2) ====
  1. Crear registro
  2. Consultar registros
  3. Estado de los servidores
  4. Ver historial local (SQLite)
  0. Salir
"""


def interactive():
    while True:
        print(MENU)
        option = input("Opción: ").strip()
        if option == "1":
            payload = input("Contenido del registro: ").strip()
            if payload:
                cmd_create(argparse.Namespace(payload=payload, server="auto"))
        elif option == "2":
            cmd_list(argparse.Namespace(server="auto", limit=20))
        elif option == "3":
            cmd_status(None)
        elif option == "4":
            cmd_history(argparse.Namespace(limit=20))
        elif option == "0":
            print("Hasta luego.")
            break
        else:
            print("Opción no válida.")


# --- entrada --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cliente del sistema distribuido de registros (Fase 2)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("create", help="crear un registro en un servidor")
    p.add_argument("--payload", required=True, help="contenido del registro")
    p.add_argument("--server", choices=["1", "2", "auto"], default="auto",
                   help="servidor preferido; con conmutación por fallo (default: auto)")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("list", help="consultar los registros de un servidor")
    p.add_argument("--server", choices=["1", "2", "auto"], default="auto")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="estado de ambos servidores")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("history", help="historial local de comunicaciones (SQLite)")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_history)

    args = parser.parse_args()
    if args.command is None:
        interactive()
    else:
        sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
