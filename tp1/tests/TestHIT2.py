import unittest
import subprocess
import time


class TestTCPReconnection(unittest.TestCase):
    SERVER_PATH = "../HIT2/server_b.py"
    CLIENT_PATH = "../HIT2/client_a.py"

    def test_flujo_reconexion(self):
        print("\n--- Iniciando Test de Reconexión ---")

        # 1. Iniciar Servidor B (Agregamos '-u' para que Python imprima al instante)
        server_p = subprocess.Popen(["python", "-u", self.SERVER_PATH], stdout=subprocess.PIPE, text=True)
        time.sleep(1)

        # 2. Iniciar Cliente A (También con '-u')
        client_p = subprocess.Popen(["python", "-u", self.CLIENT_PATH], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        print("[Test] Verificando primera conexión...")
        time.sleep(2)

        # 3. Matar el Servidor B
        print("[Test] Matando Servidor B...")
        server_p.terminate()
        server_p.wait()

        # 4. Esperar a que el cliente detecte el error
        print("[Test] Esperando a que el cliente detecte la caída (delay 3s)...")
        time.sleep(5)

        # 5. Volver a levantar el Servidor B
        print("[Test] Reiniciando Servidor B...")
        server_p_v2 = subprocess.Popen(["python", "-u", self.SERVER_PATH], stdout=subprocess.PIPE, text=True)

        # 6. Darle tiempo al cliente para conectarse de nuevo
        time.sleep(5)

        # Limpieza: Cerramos todo
        client_p.terminate()
        server_p_v2.terminate()

        # Leemos la salida del cliente y limpiamos los servidores para evitar "ResourceWarnings"
        stdout_client, _ = client_p.communicate()
        server_p_v2.communicate()

        # --- VALIDACIONES ---

        self.assertTrue(
            "Error de conexion" in stdout_client or "Reintentando" in stdout_client,
            f"El cliente no parece haber detectado la caída. Salida capturada: '{stdout_client}'",
        )

        conteo_conexiones = stdout_client.count("Conexion establecida")
        self.assertGreaterEqual(conteo_conexiones, 2, f"Se esperaba al menos 2 conexiones exitosas, pero hubo {conteo_conexiones}.")

        print(f"✅ Test pasado: El cliente A se reconectó {conteo_conexiones} veces correctamente.")


if __name__ == "__main__":
    unittest.main()
