import unittest
import subprocess
import time
import os
import sys


class TestTCPCommunication(unittest.TestCase):
    # 1. Obtener la ruta absoluta del directorio 'tp1'
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 2. Armar las rutas absolutas a los scripts
    SERVER_PATH = os.path.join(BASE_DIR, "HIT1", "server_b.py")
    CLIENT_PATH = os.path.join(BASE_DIR, "HIT1", "client_a.py")

    def test_intercambio_mensajes(self):
        # 3. Usar sys.executable en lugar de 'python3'
        server_process = subprocess.Popen([sys.executable, self.SERVER_PATH], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Pequeña pausa para asegurar que el servidor esté escuchando
        time.sleep(1.5)

        try:
            # 4. Usar sys.executable para el cliente también
            client_result = subprocess.run([sys.executable, self.CLIENT_PATH], capture_output=True, text=True, timeout=5)

            # (Opcional pero recomendado) Mostrar errores si el cliente falló al ejecutarse
            if client_result.returncode != 0:
                print(f"\n[DEBUG] Error en cliente: {client_result.stderr}")

            # Terminar el servidor y capturar su salida
            server_process.terminate()
            stdout_server, stderr_server = server_process.communicate(timeout=2)

            # (Opcional pero recomendado) Mostrar errores si el servidor falló al ejecutarse
            if stderr_server:
                print(f"\n[DEBUG] Error en servidor: {stderr_server}")

            # --- VALIDACIONES ---

            # Verificar saludo recibido por el Cliente A
            self.assertIn("Hola A, soy B. Saludo recibido!", client_result.stdout, "El cliente no recibió la respuesta esperada del servidor.")

            # Verificar mensaje recibido por el Servidor B
            self.assertIn("Hola B, soy A!", stdout_server, "El servidor no registró el saludo correcto del cliente.")

            print("\nTest pasado: La comunicación TCP entre A y B es correcta.")

        except subprocess.TimeoutExpired:
            server_process.kill()
            self.fail("El test falló por timeout (posible bloqueo en los sockets).")


if __name__ == "__main__":
    unittest.main()
