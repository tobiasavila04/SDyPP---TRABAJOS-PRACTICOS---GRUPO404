"""
HIT #6 - Nodo C: se registra en D y saluda a sus peers
Arranca en un puerto aleatorio, informa su direccion a D,
recibe la lista de peers activos y los saluda en JSON.

Uso:
    python3 node_c.py --registry-host <ip_D> --registry-port <tcp_port_D>
                      [--own-host <mi_ip_visible>]
"""

import argparse
import json
import socket
import threading
import time
from datetime import datetime, timezone

RECONNECT_DELAY = 2


# ---------------------------------------------------------------------------
# Helpers JSON/TCP (mismo framing que HIT #5)
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
# Servidor de saludos (thread)
# ---------------------------------------------------------------------------


def server_thread(listen_port: int) -> None:
    """Escucha saludos entrantes de otros nodos C."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", listen_port))
        srv.listen(10)
        print(f"[C-SERVER] Escuchando saludos en puerto {listen_port}")
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
            resp = {
                "type": "greeting_response",
                "from_port": own_port,
                "message": f"Saludo recibido de puerto {msg.get('from_port')}.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            send_json(conn, resp)
        except (ConnectionResetError, BrokenPipeError, ConnectionError, OSError) as e:
            print(f"[C-SERVER] Error con {addr}: {e}")


# ---------------------------------------------------------------------------
# Registro en D y saludo a peers
# ---------------------------------------------------------------------------


def register_and_greet(registry_host: str, registry_port: int, own_host: str, own_port: int) -> None:
    """Se registra en D y saluda a todos los peers que D devuelve."""
    attempt = 1
    while True:
        print(f"[C] Intento #{attempt} registrandose en D ({registry_host}:{registry_port})...")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((registry_host, registry_port))
                send_json(sock, {"type": "register", "host": own_host, "port": own_port})
                response = recv_json(sock)

            peers = response.get("peers", [])
            print(f"[C] Registrado en D. Peers activos: {len(peers)}")
            for peer in peers:
                _greet_peer(peer["host"], peer["port"], own_port)
            return

        except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
            print(f"[C] Error al registrarse: {e}. Reintentando en {RECONNECT_DELAY}s...")
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
            print(f"[C-CLIENT] Saludo enviado a {host}:{port}: {json.dumps(greeting)}")
            resp = recv_json(sock)
            print(f"[C-CLIENT] Respuesta de {host}:{port}: {json.dumps(resp)}")
    except OSError as e:
        print(f"[C-CLIENT] No se pudo saludar a {host}:{port} — {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _get_own_ip() -> str:
    """Obtiene la IP local visible (fallback a 127.0.0.1)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Nodo C con registro en D (HIT #6)")
    parser.add_argument("--registry-host", required=True, help="IP del nodo D")
    parser.add_argument("--registry-port", type=int, required=True, help="Puerto TCP de D")
    parser.add_argument(
        "--own-host",
        default=None,
        help="IP propia visible por D (auto-detectada si no se indica)",
    )
    args = parser.parse_args()

    own_host = args.own_host or _get_own_ip()

    # Puerto aleatorio: bind a :0 y leer el puerto asignado por el SO
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tmp:
        tmp.bind(("0.0.0.0", 0))
        own_port = tmp.getsockname()[1]

    print(f"[C] Iniciando en {own_host}:{own_port}")

    threading.Thread(
        target=server_thread,
        args=(own_port,),
        daemon=True,
        name="c-server",
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


if __name__ == "__main__":
    main()
