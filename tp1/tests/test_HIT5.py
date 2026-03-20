import unittest
import subprocess
import time


class TestJSONSerialization(unittest.TestCase):
    # Actualizamos la ruta a la carpeta del HIT5
    NODE_PATH = "../HIT5/node_c.py"

    def test_intercambio_json(self):
        print("\n--- Iniciando Test de Serialización JSON (HIT 5) ---")

        # 1. Armamos los comandos igual que en el HIT 4
        cmd_c1 = ["python", "-u", self.NODE_PATH, "--listen-port", "9001", "--remote-host", "127.0.0.1", "--remote-port", "9002"]

        cmd_c2 = ["python", "-u", self.NODE_PATH, "--listen-port", "9002", "--remote-host", "127.0.0.1", "--remote-port", "9001"]

        # 2. Levantamos la Instancia C1 primero
        print("[Test] Levantando Instancia C1...")
        p_c1 = subprocess.Popen(cmd_c1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Le damos un tiempito para que arranque y empiece a reintentar
        time.sleep(2)

        # 3. Levantamos la Instancia C2
        print("[Test] Levantando Instancia C2...")
        p_c2 = subprocess.Popen(cmd_c2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Le damos tiempo para que se conecten, serialicen el JSON y se respondan
        print("[Test] Esperando el intercambio de mensajes JSON...")
        time.sleep(4)

        # 4. Limpieza: matamos los procesos
        print("[Test] Cerrando nodos y analizando las respuestas...")
        p_c1.terminate()
        p_c2.terminate()

        # Capturamos lo que imprimió cada uno
        out_c1, _ = p_c1.communicate()
        out_c2, _ = p_c2.communicate()

        # --- VALIDACIONES ---

        # A) Chequear que C1 envió o recibió un mensaje de tipo "greeting" (saludo inicial)
        self.assertTrue('"type": "greeting"' in out_c1, f"No se encontró un JSON de tipo 'greeting' en C1. Salida: {out_c1}")

        # B) Chequear que C1 envió o recibió un mensaje de tipo "greeting_response" (la respuesta)
        self.assertTrue('"type": "greeting_response"' in out_c1, f"No se encontró un JSON de tipo 'greeting_response' en C1. Salida: {out_c1}")

        # C) Chequear que los puertos están viajando dentro del JSON
        # Si C1 (puerto 9001) recibió algo de C2, tiene que tener el puerto 9002 adentro del JSON
        self.assertTrue('"from_port": 9002' in out_c1, "C1 no parece haber recibido correctamente el puerto de origen (9002) en formato JSON.")

        # D) Chequear que el timestamp está viajando
        self.assertTrue('"timestamp":' in out_c2, "No se encontró el campo 'timestamp' en los mensajes recibidos por C2.")

        print("✅ Test pasado: Los nodos se comunicaron correctamente usando el formato JSON.")


if __name__ == "__main__":
    unittest.main()
