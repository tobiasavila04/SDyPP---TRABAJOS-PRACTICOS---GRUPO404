"""
HIT #1 - Nodo B: Servidor TCP
Espera el saludo del nodo A y responde.
"""

import socket

HOST = "0.0.0.0"
PORT = 9000


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((HOST, PORT))
        server_sock.listen(1)
        print(f"[B] Servidor escuchando en {HOST}:{PORT}")

        conn, addr = server_sock.accept()
        with conn:
            print(f"[B] Conexion aceptada desde {addr}")
            data = conn.recv(1024)
            if data:
                mensaje = data.decode()
                print(f"[B] Recibi: {mensaje}")
                respuesta = "Hola A, soy B. Saludo recibido!"
                conn.sendall(respuesta.encode())
                print(f"[B] Respuesta enviada: {respuesta}")

        print("[B] Conexion cerrada.")


if __name__ == "__main__":
    main()
