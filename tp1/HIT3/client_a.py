"""
HIT #3 - Nodo A: Cliente TCP
Se conecta a B, saluda y queda en espera.
Matar este proceso (Ctrl+C / kill) simula una desconexion abrupta
para probar que B sigue funcionando.
"""

import socket
import time

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        print(f"[A] Conectando a {SERVER_HOST}:{SERVER_PORT}...")
        sock.connect((SERVER_HOST, SERVER_PORT))
        print("[A] Conexion establecida.")

        saludo = "Hola B, soy A!"
        sock.sendall(saludo.encode())
        print(f"[A] Saludo enviado: {saludo}")

        respuesta = sock.recv(1024)
        print(f"[A] Respuesta de B: {respuesta.decode()}")

        print("[A] Manteniendo conexion abierta... (mata este proceso para probar HIT #3)")
        while True:
            time.sleep(1)


if __name__ == "__main__":
    main()
