"""
HIT #2 - Nodo A: Cliente TCP con reconexion automatica
Se conecta a B, saluda, y si B cierra la conexion (o no esta disponible)
reintenta automaticamente hasta restablecer la comunicacion.
"""

import socket
import time

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9000
RECONNECT_DELAY = 3  # segundos entre intentos


def saludar(sock):
    saludo = "Hola B, soy A!"
    sock.sendall(saludo.encode())
    print(f"[A] Saludo enviado: {saludo}")

    respuesta = sock.recv(1024)
    if not respuesta:
        raise ConnectionError("B cerro la conexion sin responder.")
    print(f"[A] Respuesta de B: {respuesta.decode()}")


def main():
    intento = 1
    while True:
        print(f"[A] Intento #{intento} — conectando a {SERVER_HOST}:{SERVER_PORT}...")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((SERVER_HOST, SERVER_PORT))
                print("[A] Conexion establecida.")
                saludar(sock)
                print("[A] Intercambio completado. Esperando para reconectar...\n")
        except (
            ConnectionRefusedError,
            ConnectionResetError,
            ConnectionError,
            OSError,
        ) as e:
            print(f"[A] Error de conexion: {e}")
            print(f"[A] Reintentando en {RECONNECT_DELAY} segundos...\n")

        intento += 1
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()
