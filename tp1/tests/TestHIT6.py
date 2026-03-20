import unittest
import subprocess
import time
import urllib.request
import json


class TestNodeDRegistry(unittest.TestCase):
    def test_registro_y_descubrimiento(self):
        print("\n--- Iniciando Test del Registro de Contactos (HIT 6) ---")

        # 1. Levantar Nodo D (API HTTP + Registro TCP)
        # Usamos 'python -m uvicorn' por si el comando 'uvicorn' suelto no está en el PATH de Windows
        print("[Test] Levantando Nodo D (API en puerto 8080, TCP en 9000)...")
        cmd_d = ["python", "-m", "uvicorn", "HIT6.node_d:app", "--host", "127.0.0.1", "--port", "8080"]

        # cwd='..' ejecuta el comando desde la carpeta tp1 para que encuentre bien el módulo
        p_d = subprocess.Popen(cmd_d, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd="..")

        time.sleep(3)  # Esperar a que Uvicorn arranque y abra los puertos

        # 2. Levantar Nodo C1
        print("[Test] Levantando Nodo C1...")
        cmd_c = ["python", "-u", "HIT6/node_c.py", "--registry-host", "127.0.0.1", "--registry-port", "9000"]
        p_c1 = subprocess.Popen(cmd_c, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd="..")

        time.sleep(2)  # Dar tiempo a que se registre

        # 3. Levantar Nodo C2
        print("[Test] Levantando Nodo C2...")
        p_c2 = subprocess.Popen(cmd_c, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd="..")

        time.sleep(3)  # Dar tiempo a que C2 se registre, pida la lista y salude a C1

        # --- VALIDACIONES HTTP ---
        print("[Test] Consultando la API HTTP del Nodo D...")
        try:
            # Le pegamos al endpoint /health para ver si registró a los 2 nodos
            with urllib.request.urlopen("http://127.0.0.1:8080/health") as response:
                data = json.loads(response.read().decode())
                nodos_registrados = data.get("registered_nodes", 0)

                self.assertEqual(nodos_registrados, 2, f"Se esperaban 2 nodos registrados en la API, pero hay {nodos_registrados}.")
                print("✅ API HTTP validada: detectó los 2 nodos correctamente.")
        except Exception as e:
            # Si falla esto, asegurate de matar los procesos para que no queden colgados
            p_d.terminate()
            p_c1.terminate()
            p_c2.terminate()
            self.fail(f"Falló la conexión a la API HTTP del Nodo D: {e}")

        # Limpieza general
        print("[Test] Cerrando nodos y analizando salidas...")
        p_c1.terminate()
        p_c2.terminate()
        p_d.terminate()

        out_c1, _ = p_c1.communicate()
        out_c2, _ = p_c2.communicate()
        p_d.communicate()

        # --- VALIDACIONES TCP / CONSOLA ---
        # C2 debería haber recibido una lista de peers (que incluye a C1) y haber intentado contactarlo
        self.assertTrue(
            "saludo" in out_c2.lower() or "json" in out_c2.lower(), f"C2 no parece haber intentado contactar a C1. Salida de C2: {out_c2}"
        )

        print("✅ Test pasado: El Nodo D registró a los clientes y C2 descubrió a C1.")


if __name__ == "__main__":
    unittest.main()
