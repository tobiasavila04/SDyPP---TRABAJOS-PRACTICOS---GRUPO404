"""
HIT #4 - Nodo C: Cliente y Servidor TCP simultaneos
Funciona como servidor (escucha saludos) y como cliente (saluda al otro C)
al mismo tiempo, usando un thread por rol.

Uso:
    python3 node_c.py --listen-port <puerto_propio> \
                      --remote-host <ip_otro_c>     \
                      --remote-port <puerto_otro_c>
"""

import argparse
import socket
import threading
import time

RECONNECT_DELAY = 2


def server_thread(listen_host, listen_port):
    """Escucha conexiones entrantes y responde saludos indefinidamente."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((listen_host, listen_port))
        srv.listen(5)
        print(f"[C-SERVER] Escuchando en {listen_host}:{listen_port}")

        while True:
            try:
                conn, addr = srv.accept()
                with conn:
                    data = conn.recv(1024)
                    if not data:
                        continue
                    mensaje = data.decode()
                    print(f"[C-SERVER] Recibi de {addr}: {mensaje}")
                    respuesta = f"Hola! Soy C en puerto {listen_port}. Saludo recibido."
                    conn.sendall(respuesta.encode())
                    print(f"[C-SERVER] Respuesta enviada a {addr}")
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f"[C-SERVER] Error con cliente: {e}")


def client_thread(remote_host, remote_port, own_port):
    """Se conecta al otro nodo C y le envia un saludo.

    Reintenta si no esta disponible.
    """
    attempt = 1
    while True:
        print(
            f"[C-CLIENT] Intento #{attempt} conectando a {remote_host}:{remote_port}..."
        )
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((remote_host, remote_port))
                saludo = f"Hola! Soy C en puerto {own_port}."
                sock.sendall(saludo.encode())
                print(f"[C-CLIENT] Saludo enviado: {saludo}")
                respuesta = sock.recv(1024)
                print(
                    f"[C-CLIENT] Respuesta de {remote_host}:{remote_port}: "
                    f"{respuesta.decode()}"
                )
                return  # saludo completado, el cliente termina
        except (ConnectionRefusedError, ConnectionResetError, OSError) as e:
            print(f"[C-CLIENT] Error: {e}. Reintentando en {RECONNECT_DELAY}s...")
            attempt += 1
            time.sleep(RECONNECT_DELAY)


def main():
    parser = argparse.ArgumentParser(description="Nodo C bidireccional (HIT #4)")
    parser.add_argument(
        "--listen-host", default="0.0.0.0", help="IP donde escuchar (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--listen-port", type=int, required=True, help="Puerto propio de escucha"
    )
    parser.add_argument("--remote-host", required=True, help="IP del otro nodo C")
    parser.add_argument(
        "--remote-port", type=int, required=True, help="Puerto del otro nodo C"
    )
    args = parser.parse_args()

    srv = threading.Thread(
        target=server_thread,
        args=(args.listen_host, args.listen_port),
        daemon=True,
        name="server",
    )
    cli = threading.Thread(
        target=client_thread,
        args=(args.remote_host, args.remote_port, args.listen_port),
        daemon=True,
        name="client",
    )

    srv.start()
    cli.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[C] Terminando.")


if __name__ == "__main__":
    main()
