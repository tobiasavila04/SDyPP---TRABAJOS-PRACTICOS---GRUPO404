"""
HIT #6 - Nodo D: Registro de Contactos
Expone:
  - Servidor TCP en TCP_PORT  → los nodos C se registran aqui
  - HTTP GET /health          → estado del servicio (uptime, nodos registrados)
  - HTTP GET /nodes           → lista de nodos C activos

Uso:
    uvicorn tp1.HIT6.node_d:app --host 0.0.0.0 --port 8080
    (el servidor TCP arranca automaticamente al importar el modulo)
"""

import os
import socket
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

TCP_HOST = "0.0.0.0"
TCP_PORT = int(os.getenv("TCP_PORT", "9000"))

# ---------------------------------------------------------------------------
# Estado en memoria
# ---------------------------------------------------------------------------

_start_time = time.time()
_registry: list[dict] = []  # [{host, port, registered_at}]
_registry_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers JSON/TCP (mismo framing que HIT #5)
# ---------------------------------------------------------------------------


def _send_json(sock: socket.socket, payload: dict) -> None:
    import json

    sock.sendall((json.dumps(payload) + "\n").encode())


def _recv_json(sock: socket.socket) -> dict:
    import json

    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Conexion cerrada antes de recibir mensaje.")
        buf += chunk
    return json.loads(buf.split(b"\n")[0].decode())


# ---------------------------------------------------------------------------
# Servidor TCP de registro
# ---------------------------------------------------------------------------


def _handle_registration(conn: socket.socket, addr: tuple) -> None:
    with conn:
        msg = _recv_json(conn)
        if msg.get("type") != "register":
            print(f"[D-TCP] Mensaje inesperado de {addr}: {msg}")
            return

        node = {
            "host": msg["host"],
            "port": msg["port"],
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        with _registry_lock:
            peers = [n for n in _registry if n["host"] != node["host"] or n["port"] != node["port"]]
            _registry.append(node)
            peers_snapshot = list(peers)

        print(f"[D-TCP] Nodo registrado: {node['host']}:{node['port']} — total: {len(_registry)}")
        _send_json(conn, {"type": "registered", "peers": peers_snapshot})


def _tcp_server() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((TCP_HOST, TCP_PORT))
        srv.listen(10)
        print(f"[D-TCP] Servidor de registro escuchando en {TCP_HOST}:{TCP_PORT}")
        while True:
            try:
                conn, addr = srv.accept()
                t = threading.Thread(
                    target=_handle_registration,
                    args=(conn, addr),
                    daemon=True,
                )
                t.start()
            except OSError:
                break


# Arrancar TCP en background al importar el modulo
threading.Thread(target=_tcp_server, daemon=True, name="tcp-registry").start()

# ---------------------------------------------------------------------------
# FastAPI — endpoints HTTP
# ---------------------------------------------------------------------------

app = FastAPI(title="SD2026-GRUPO404 Node D — Registro de Contactos", version="1.0.0")


@app.get("/")
def root():
    return {"service": "node-d", "status": "running"}


@app.get("/health")
def health():
    with _registry_lock:
        count = len(_registry)
    return {
        "status": "healthy",
        "registered_nodes": count,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "tcp_registry_port": TCP_PORT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/nodes")
def list_nodes():
    with _registry_lock:
        nodes = list(_registry)
    return {"count": len(nodes), "nodes": nodes}


@app.delete("/nodes")
def clear_nodes():
    """Limpia el registro (util para testing)."""
    with _registry_lock:
        _registry.clear()
    return {"message": "Registro limpiado."}
