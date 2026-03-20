import unittest
import subprocess
import time


class TestBidirectionalNode(unittest.TestCase):
    NODE_PATH = "../HIT4/node_c.py"

    def test_comunicacion_mutua(self):
        print("\n--- Iniciando Test de Nodo C Bidireccional (HIT 4) ---")

        # 1. Armamos los comandos exactos que pasaste en la descripción
        cmd_c1 = ["python", "-u", self.NODE_PATH, "--listen-port", "9001", "--remote-host", "127.0.0.1", "--remote-port", "9002"]

        cmd_c2 = ["python", "-u", self.NODE_PATH, "--listen-port", "9002", "--remote-host", "127.0.0.1", "--remote-port", "9001"]

        # 2. Levantamos la Instancia C1 primero
        print("[Test] Levantando Instancia C1 (escucha en 9001, busca 9002)...")
        p_c1 = subprocess.Popen(cmd_c1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Le damos 3 segundos a propósito para que el cliente de C1 falle y entre en el loop de reintentos
        time.sleep(3)

        # 3. Levantamos la Instancia C2
        print("[Test] Levantando Instancia C2 (escucha en 9002, busca 9001)...")
        p_c2 = subprocess.Popen(cmd_c2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Le damos tiempo para que el cliente de C2 conecte de una, y el cliente de C1 enganche en su próximo reintento
        print("[Test] Esperando a que se encuentren y charlen...")
        time.sleep(4)

        # 4. Limpieza: cerramos todo
        print("[Test] Matando procesos y analizando salidas...")
        p_c1.terminate()
        p_c2.terminate()

        # Leemos qué imprimió cada uno
        out_c1, _ = p_c1.communicate()
        out_c2, _ = p_c2.communicate()

        # --- VALIDACIONES ---

        # A) Comprobar que C1 tuvo que reintentar la conexión al estar solo
        self.assertTrue(
            "Reintentando" in out_c1 or "Connection refused" in out_c1,
            f"C1 arrancó primero, debió haber mostrado el error de conexión y reintento. Salida: {out_c1}",
        )

        # B) Comprobar que C1 recibió el saludo que venía de C2
        self.assertIn("Hola! Soy C en puerto 9002", out_c1, "C1 no registró haber recibido el saludo de C2.")

        # C) Comprobar que C2 recibió el saludo que venía de C1
        self.assertIn("Hola! Soy C en puerto 9001", out_c2, "C2 no registró haber recibido el saludo de C1.")

        print("✅ Test pasado: C1 reintentó correctamente y ambos nodos se saludaron de forma bidireccional.")


if __name__ == "__main__":
    unittest.main()
