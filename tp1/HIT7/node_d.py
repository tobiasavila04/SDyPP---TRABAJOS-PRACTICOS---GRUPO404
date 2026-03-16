"""
HIT #7 - Nodo D: Sistema de Inscripciones con ventanas de 1 minuto

Logica de ventanas:
  - _current_window : nodos activos en la ventana actual (visibles para C)
  - _next_window    : nodos inscriptos para la proxima ventana (no visibles aun)
  Cada 60 s (al cambio de minuto): _current = _next, _next = []

Cada transicion de ventana se persiste en inscripciones.json.

Endpoints HTTP:
  GET  /health           estado + info de ventana actual
  GET  /window/current   nodos de la ventana actual
  GET  /window/next      nodos inscriptos para la proxima ventana
  GET  /windows          historial completo de ventanas (del archivo JSON)
  DELETE /windows        limpia historial y estado en memoria (testing)

Uso:
    uvicorn tp1.HIT7.node_d:app --host 0.0.0.0 --port 8080
"""

import json
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

TCP_HOST = "0.0.0.0"
TCP_PORT = int(os.getenv("TCP_PORT", "9000"))
INSCRIPCIONES_FILE = Path(os.getenv("INSCRIPCIONES_FILE", "inscripciones.json"))

# ---------------------------------------------------------------------------
# Estado en memoria
# ---------------------------------------------------------------------------

_start_time = time.time()
_lock = threading.Lock()

_current_window: list[dict] = []  # nodos activos ahora
_next_window: list[dict] = []  # nodos para la proxima ventana
_current_window_start: str = ""  # ISO timestamp de inicio de ventana actual


def _next_minute_iso() -> str:
    """Retorna el ISO timestamp del proximo minuto exacto en UTC."""
    now = datetime.now(timezone.utc)
    next_min = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    return next_min.isoformat()


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


def _load_history() -> list[dict]:
    if INSCRIPCIONES_FILE.exists():
        with open(INSCRIPCIONES_FILE) as f:
            return json.load(f)
    return []


def _save_window(window_start: str, nodes: list[dict]) -> None:
    """Agrega una entrada de ventana al archivo JSON de inscripciones."""
    history = _load_history()
    history.append(
        {
            "window_start": window_start,
            "window_end": _next_minute_iso(),
            "node_count": len(nodes),
            "nodes": nodes,
        }
    )
    with open(INSCRIPCIONES_FILE, "w") as f:
        json.dump(history, f, indent=2)
    print(f"[D] Ventana guardada en {INSCRIPCIONES_FILE}: {len(nodes)} nodo(s)")


# ---------------------------------------------------------------------------
# Gestor de ventanas (thread)
# ---------------------------------------------------------------------------


def _window_manager() -> None:
    """Cada segundo verifica si cambio el minuto. Si cambio, rota ventanas."""
    global _current_window, _next_window, _current_window_start
    last_minute = datetime.now(timezone.utc).minute

    while True:
        time.sleep(1)
        now = datetime.now(timezone.utc)
        if now.minute != last_minute:
            last_minute = now.minute
            with _lock:
                # Persistir ventana que acaba de cerrar
                _save_window(_current_window_start, _current_window)
                # Rotar
                _current_window = list(_next_window)
                _next_window = []
                _current_window_start = now.replace(second=0, microsecond=0).isoformat()

            print(
                f"[D] Nueva ventana activa desde {_current_window_start} "
                f"con {len(_current_window)} nodo(s)"
            )


# Inicializar timestamp de ventana actual al arrancar
_current_window_start = (
    datetime.now(timezone.utc).replace(second=0, microsecond=0).isoformat()
)

threading.Thread(target=_window_manager, daemon=True, name="window-manager").start()

# ---------------------------------------------------------------------------
# Helpers JSON/TCP
# ---------------------------------------------------------------------------


def _send_json(sock: socket.socket, payload: dict) -> None:
    sock.sendall((json.dumps(payload) + "\n").encode())


def _recv_json(sock: socket.socket) -> dict:
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Conexion cerrada antes de recibir mensaje.")
        buf += chunk
    return json.loads(buf.split(b"\n")[0].decode())


# ---------------------------------------------------------------------------
# Servidor TCP de inscripciones
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

        with _lock:
            # Evitar duplicados en next_window
            already = any(
                n["host"] == node["host"] and n["port"] == node["port"]
                for n in _next_window
            )
            if not already:
                _next_window.append(node)

            current_peers = list(_current_window)
            next_window_start = _next_minute_iso()

        print(
            f"[D-TCP] Inscripto para {next_window_start}: "
            f"{node['host']}:{node['port']} "
            f"— siguiente ventana: {len(_next_window)} nodo(s)"
        )

        _send_json(
            conn,
            {
                "type": "registered",
                "assigned_window": next_window_start,
                "peers": current_peers,  # peers de la ventana ACTUAL (no la futura)
            },
        )


def _tcp_server() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((TCP_HOST, TCP_PORT))
        srv.listen(10)
        print(f"[D-TCP] Servidor de inscripciones en {TCP_HOST}:{TCP_PORT}")
        while True:
            try:
                conn, addr = srv.accept()
                threading.Thread(
                    target=_handle_registration,
                    args=(conn, addr),
                    daemon=True,
                ).start()
            except OSError:
                break


threading.Thread(target=_tcp_server, daemon=True, name="tcp-registry").start()

# ---------------------------------------------------------------------------
# FastAPI — endpoints HTTP
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SD2026-GRUPO404 Node D — Sistema de Inscripciones", version="2.0.0"
)


@app.get("/")
def root():
    return {"service": "node-d", "hit": 7, "status": "running"}


@app.get("/health")
def health():
    with _lock:
        current_count = len(_current_window)
        next_count = len(_next_window)
        window_start = _current_window_start

    return {
        "status": "healthy",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "tcp_registry_port": TCP_PORT,
        "current_window": {
            "start": window_start,
            "node_count": current_count,
        },
        "next_window": {
            "start": _next_minute_iso(),
            "node_count": next_count,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/window/current")
def current_window():
    with _lock:
        return {
            "window_start": _current_window_start,
            "node_count": len(_current_window),
            "nodes": list(_current_window),
        }


@app.get("/window/next")
def next_window_view():
    with _lock:
        return {
            "window_start": _next_minute_iso(),
            "node_count": len(_next_window),
            "nodes": list(_next_window),
        }


@app.get("/windows")
def windows_history():
    """Historial completo de ventanas persistido en disco."""
    return {"windows": _load_history()}


@app.delete("/windows")
def clear_windows():
    """Limpia estado en memoria y archivo (para testing)."""
    global _current_window, _next_window
    with _lock:
        _current_window = []
        _next_window = []
    if INSCRIPCIONES_FILE.exists():
        INSCRIPCIONES_FILE.write_text("[]")
    return {"message": "Estado e historial limpiados."}
