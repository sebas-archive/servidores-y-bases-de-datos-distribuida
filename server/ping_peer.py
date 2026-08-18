"""Utilidad de diagnóstico: envía un PING por el canal TCP al servidor par.

Uso (dentro de un contenedor de servidor):
  python3 ping_peer.py          # usa PEER_HOST y PEER_PORT del entorno
  python3 ping_peer.py host puerto

Ejemplo de salida:
  {"type": "PONG", "server_id": "server2", "record_count": 3}
"""

import json
import os
import socket
import sys

from replication import PING, send_tcp


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PEER_HOST")
    port = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.environ.get("PEER_PORT", "6000"))
    if not host:
        print("Uso: python3 ping_peer.py <host> <puerto>")
        return 1

    try:
        replies = send_tcp(host, port, [{"type": PING}], timeout=3)
        print(json.dumps(replies[0], ensure_ascii=False) if replies else "(sin respuesta)")
    except OSError as exc:
        print(f"Sin respuesta de {host}:{port} ({exc.__class__.__name__})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
