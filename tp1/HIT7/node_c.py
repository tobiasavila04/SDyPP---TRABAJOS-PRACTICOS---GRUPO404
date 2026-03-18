"""
HIT #7 - Nodo C: Sistema de Inscripciones
Se registra en D para la proxima ventana de tiempo.
Recibe los peers de la ventana ACTUAL y los saluda.
No conoce a priori a sus pares de la proxima ventana.

Uso:
    python3 node_c.py --registry-host <ip_D> --registry-port <tcp_port_D>
                      [--own-host <mi_ip_visible>]
"""

import argparse
import json
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

RECONNECT_DELAY = 2


# ---------------------------------------------------------------------------
# Helpers JSON/TCP
# ---------------------------------------------------------------------------


def send_json(sock: socket.socket, payload: dict) -> None:
    """Serializa payload como JSON y lo envia terminado en newline."""
    sock.sendall((json.dumps(payload) + "\n").encode())


def recv_json(sock: socket.socket) -> dict:
    """Lee hasta newline y deserializa JSON."""
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Conexion cerrada antes de recibir mensaje.")
        buf += chunk
    return json.loads(buf.split(b"\n")[0].decode())


# ---------------------------------------------------------------------------
# Servidor de saludos
# ---------------------------------------------------------------------------


def server_thread(srv: socket.socket, listen_port: int) -> None:
    """Escucha saludos entrantes de otros nodos C."""
    with srv:
        print(f"[C-SERVER] Escuchando en puerto {listen_port}")
        while True:
            try:
                conn, addr = srv.accept()
                threading.Thread(
                    target=_handle_greeting,
                    args=(conn, addr, listen_port),
                    daemon=True,
                ).start()
            except (ConnectionResetError, OSError) as e:
                print(f"[C-SERVER] Error: {e}")


def _handle_greeting(conn: socket.socket, addr: tuple, own_port: int) -> None:
    with conn:
        try:
            msg = recv_json(conn)
            print(f"[C-SERVER] Saludo de {addr}: {json.dumps(msg)}")
            send_json(
                conn,
                {
                    "type": "greeting_response",
                    "from_port": own_port,
                    "message": f"Saludo recibido de puerto {msg.get('from_port')}.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except (ConnectionResetError, BrokenPipeError, ConnectionError, OSError) as e:
            print(f"[C-SERVER] Error con {addr}: {e}")


# ---------------------------------------------------------------------------
# Inscripcion en D y saludo a peers de ventana actual
# ---------------------------------------------------------------------------


def register_and_greet(
    registry_host: str, registry_port: int, own_host: str, own_port: int
) -> None:
    """Se inscribe en D para la proxima ventana y saluda a los peers actuales."""
    attempt = 1
    while True:
        print(
            f"[C] Intento #{attempt} — inscribiendose en D "
            f"({registry_host}:{registry_port})..."
        )
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((registry_host, registry_port))
                send_json(
                    sock, {"type": "register", "host": own_host, "port": own_port}
                )
                response = recv_json(sock)

            assigned = response.get("assigned_window", "desconocida")
            peers = response.get("peers", [])

            print(f"[C] Inscripto para ventana: {assigned}")
            print(f"[C] Peers en ventana actual: {len(peers)}")

            for peer in peers:
                if peer["host"] == own_host and peer["port"] == own_port:
                    continue
                _greet_peer(peer["host"], peer["port"], own_port)

            window_end = datetime.fromisoformat(assigned) + timedelta(minutes=1)
            sleep_until = window_end - timedelta(seconds=10)
            now = datetime.now(timezone.utc)
            wait = (sleep_until - now).total_seconds()
            if wait > 0:
                print(f"[C] Proxima reinscripcion en {wait:.1f}s...")
                time.sleep(wait)
            attempt = 1

        except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
            print(f"[C] Error: {e}. Reintentando en {RECONNECT_DELAY}s...")
            attempt += 1
            time.sleep(RECONNECT_DELAY)


def _greet_peer(host: str, port: int, own_port: int) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
            greeting = {
                "type": "greeting",
                "from_port": own_port,
                "message": f"Hola! Soy C en puerto {own_port}.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            send_json(sock, greeting)
            print(f"[C-CLIENT] Saludo enviado a {host}:{port}")
            resp = recv_json(sock)
            print(f"[C-CLIENT] Respuesta de {host}:{port}: {json.dumps(resp)}")
    except OSError as e:
        print(f"[C-CLIENT] No se pudo saludar a {host}:{port} — {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _unregister(
    registry_host: str, registry_port: int, own_host: str, own_port: int
) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3)
            sock.connect((registry_host, registry_port))
            send_json(sock, {"type": "unregister", "host": own_host, "port": own_port})
            print("[C] Desinscripto de D.")
    except OSError:
        pass


def _get_own_ip() -> str:
    """Detecta la IP local saliente."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nodo C — Sistema de Inscripciones (HIT #7)"
    )
    parser.add_argument("--registry-host", required=True)
    parser.add_argument("--registry-port", type=int, required=True)
    parser.add_argument("--own-host", default=None)
    args = parser.parse_args()

    if args.own_host:
        own_host = args.own_host
    elif args.registry_host in ("127.0.0.1", "localhost"):
        own_host = "127.0.0.1"
    else:
        own_host = _get_own_ip()

    srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv_sock.bind(("0.0.0.0", 0))
    own_port = srv_sock.getsockname()[1]
    srv_sock.listen(10)

    print(f"[C] Iniciando en {own_host}:{own_port}")

    threading.Thread(
        target=server_thread, args=(srv_sock, own_port), daemon=True, name="c-server"
    ).start()

    threading.Thread(
        target=register_and_greet,
        args=(args.registry_host, args.registry_port, own_host, own_port),
        daemon=True,
        name="c-register",
    ).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[C] Terminando.")
        _unregister(args.registry_host, args.registry_port, own_host, own_port)


if __name__ == "__main__":
    main()