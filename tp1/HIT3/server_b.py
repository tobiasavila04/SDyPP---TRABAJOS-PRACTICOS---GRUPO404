"""
HIT #3 - Nodo B: Servidor TCP robusto
Si A cierra la conexion abruptamente, B captura el error y sigue
escuchando nuevas conexiones sin caerse.
"""

import socket

HOST = "0.0.0.0"
PORT = 9000


def handle_connection(conn, addr):
    """Atiende una conexion de A. Lanza excepcion si A se desconecta abruptamente."""
    print(f"[B] Conexion aceptada desde {addr}")
    data = conn.recv(1024)
    if not data:
        raise ConnectionError(f"A ({addr}) cerro la conexion sin enviar datos.")

    mensaje = data.decode()
    print(f"[B] Recibi: {mensaje}")

    respuesta = "Hola A, soy B. Saludo recibido!"
    conn.sendall(respuesta.encode())
    print(f"[B] Respuesta enviada: {respuesta}")


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((HOST, PORT))
        server_sock.listen(5)
        print(f"[B] Servidor escuchando en {HOST}:{PORT}")
        print("[B] Mata el proceso A para probar que B sigue funcionando.\n")

        while True:
            conn, addr = server_sock.accept()
            try:
                with conn:
                    handle_connection(conn, addr)
            except (
                ConnectionResetError,
                BrokenPipeError,
                ConnectionError,
                OSError,
            ) as e:
                print(f"[B] A se desconecto abruptamente: {e}")
            finally:
                print("[B] Conexion con A cerrada. Esperando nueva conexion...\n")


if __name__ == "__main__":
    main()
