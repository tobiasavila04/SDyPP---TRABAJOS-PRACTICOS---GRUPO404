import unittest
import subprocess
import time


class TestServerRobustness(unittest.TestCase):
    SERVER_PATH = "../HIT3/server_b.py"
    CLIENT_PATH = "../HIT3/client_a.py"

    def test_servidor_sobrevive_caida(self):
        print("\n--- Iniciando Test de Robustez del Servidor (HIT 3) ---")

        # 1. Iniciar Servidor B (siempre con '-u' para no perder los prints)
        server_p = subprocess.Popen(["python", "-u", self.SERVER_PATH], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(1)  # Dar tiempo a que abra el puerto

        # 2. Iniciar el primer Cliente A
        print("[Test] Conectando el primer Cliente A...")
        client_1 = subprocess.Popen(["python", "-u", self.CLIENT_PATH], stdout=subprocess.PIPE, text=True)
        time.sleep(2)  # Esperar que salude y se quede en el loop infinito

        # 3. Matar el primer Cliente A (simulando corte de red / Ctrl+C)
        print("[Test] Matando al primer Cliente A abruptamente...")
        client_1.terminate()
        client_1.wait()  # Esperamos a que muera por completo

        # Le damos un respiro al servidor para que capture la excepción y vuelva a escuchar
        time.sleep(2)

        # 4. Iniciar un segundo Cliente A para comprobar que B sigue trabajando
        print("[Test] Conectando un nuevo Cliente A...")
        client_2 = subprocess.Popen(["python", "-u", self.CLIENT_PATH], stdout=subprocess.PIPE, text=True)
        time.sleep(2)  # Dar tiempo a que haga el saludo

        # Limpieza general de los procesos que quedaron corriendo
        print("[Test] Limpiando procesos...")
        client_2.terminate()
        server_p.terminate()

        # Capturar las salidas y evitar los ResourceWarnings
        stdout_server, _ = server_p.communicate()
        client_1.communicate()
        client_2.communicate()

        # --- VALIDACIONES ---

        # 1. Chequear que B registró el error/desconexión del primer cliente
        # Buscamos palabras clave que indicaste en la descripción
        self.assertTrue(
            "desconecto abruptamente" in stdout_server or "cerrada" in stdout_server,
            "El servidor no parece haber registrado la caída del primer cliente.",
        )

        # 2. Chequear que B siguió vivo y aceptó una segunda conexión
        # Si todo anduvo bien, la palabra "Conexion aceptada" (o similar) debería estar 2 veces
        conteo_conexiones = stdout_server.count("Conexion")
        self.assertGreaterEqual(
            conteo_conexiones, 2, f"El servidor debía procesar al menos 2 conexiones en total, pero hubo menos. Salida del server:\n{stdout_server}"
        )

        print("✅ Test pasado: El Servidor B es de fierro y aguantó la caída de A.")


if __name__ == "__main__":
    unittest.main()
