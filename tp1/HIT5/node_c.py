"""
HIT #5 - Nodo C: mensajes en formato JSON
Extiende el HIT #4 serializando y deserializando todos los mensajes como JSON.
Los mensajes se delimitan con newline (\\n) para manejar el framing TCP.

Uso:
    python3 node_c.py --listen-port <puerto_propio> \
                      --remote-host <ip_otro_c>     \
                      --remote-port <puerto_otro_c>
"""

import argparse
import json
import socket
import threading
import time
from datetime import datetime, timezone

RECONNECT_DELAY = 2


# ---------------------------------------------------------------------------
# Helpers de serialización / deserialización
# ---------------------------------------------------------------------------


def send_json(sock, payload: dict) -> None:
    """Serializa payload como JSON y lo envía terminado en newline."""
    raw = json.dumps(payload) + "\n"
    sock.sendall(raw.encode())


def recv_json(sock) -> dict:
    """Lee bytes hasta newline y deserializa el JSON recibido."""
    buffer = b""
    while b"\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Conexion cerrada antes de recibir mensaje completo.")
        buffer += chunk
    return json.loads(buffer.split(b"\n")[0].decode())


def make_greeting(own_port: int) -> dict:
    """Construye el mensaje de saludo."""
    return {
        "type": "greeting",
        "from_port": own_port,
        "message": f"Hola! Soy C en puerto {own_port}.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def make_response(own_port: int, received: dict) -> dict:
    """Construye la respuesta al saludo."""
    return {
        "type": "greeting_response",
        "from_port": own_port,
        "message": f"Saludo recibido de puerto {received.get('from_port')}.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------


def server_thread(listen_host: str, listen_port: int) -> None:
    """Escucha conexiones entrantes, deserializa el saludo y responde en JSON."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((listen_host, listen_port))
        srv.listen(5)
        print(f"[C-SERVER] Escuchando en {listen_host}:{listen_port}")

        while True:
            try:
                conn, addr = srv.accept()
                with conn:
                    msg = recv_json(conn)
                    print(f"[C-SERVER] JSON recibido de {addr}: {json.dumps(msg)}")
                    resp = make_response(listen_port, msg)
                    send_json(conn, resp)
                    print(f"[C-SERVER] JSON enviado a {addr}: {json.dumps(resp)}")
            except (
                ConnectionResetError,
                BrokenPipeError,
                ConnectionError,
                OSError,
            ) as e:
                print(f"[C-SERVER] Error con cliente: {e}")


def client_thread(remote_host: str, remote_port: int, own_port: int) -> None:
    """Se conecta al otro C, envía saludo JSON y recibe respuesta JSON."""
    attempt = 1
    while True:
        print(f"[C-CLIENT] Intento #{attempt} conectando a {remote_host}:{remote_port}...")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((remote_host, remote_port))
                greeting = make_greeting(own_port)
                send_json(sock, greeting)
                print(f"[C-CLIENT] JSON enviado: {json.dumps(greeting)}")
                resp = recv_json(sock)
                print(f"[C-CLIENT] JSON recibido: {json.dumps(resp)}")
                return
        except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
            print(f"[C-CLIENT] Error: {e}. Reintentando en {RECONNECT_DELAY}s...")
            attempt += 1
            time.sleep(RECONNECT_DELAY)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Nodo C con mensajes JSON (HIT #5)")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--remote-host", required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    args = parser.parse_args()

    threading.Thread(
        target=server_thread,
        args=(args.listen_host, args.listen_port),
        daemon=True,
        name="server",
    ).start()

    threading.Thread(
        target=client_thread,
        args=(args.remote_host, args.remote_port, args.listen_port),
        daemon=True,
        name="client",
    ).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[C] Terminando.")


if __name__ == "__main__":
    main()
