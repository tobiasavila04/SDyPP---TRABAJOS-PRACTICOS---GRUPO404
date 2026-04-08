import argparse
import json
import os

import requests

REMOTE_URL = "http://3.144.148.19:5015/task"
LOCAL_URL = "http://localhost:5015/task"

parser = argparse.ArgumentParser(description="ejecuta operaciones matemáticas en el servidor.")

parser.add_argument(
    "--operacion",
    type=str,
    required=True,
    choices=["suma", "resta", "multiplicacion", "division"],
    help="operación a ejecutar: suma, resta, multiplicacion o division.",
)

parser.add_argument("--valores", type=float, nargs="+", required=True, help="Números sobre los que operar. Ej: --valores 10 25 7")

parser.add_argument("--remote", action="store_true", help="Conectar al servidor remoto en AWS en lugar de localhost.")

args = parser.parse_args()

SERVER_URL = REMOTE_URL if args.remote else os.environ.get("SERVER_URL", LOCAL_URL)

if args.operacion in ("suma", "resta", "multiplicacion", "division") and len(args.valores) < 2:
    print("Error: se requieren al menos 2 valores para realizar la operación.")
    exit()

PAYLOAD = {
    "operation": args.operacion,
    "values": args.valores,
}

try:
    respuesta = requests.post(f"{SERVER_URL}", json=PAYLOAD, timeout=60)
    respuesta.raise_for_status()

    resultado = respuesta.json().get("result")
    print(f"Resultado: {json.dumps(resultado, indent=2, ensure_ascii=False)}")

except requests.exceptions.ConnectionError:
    print("Error: No se pudo conectar al servidor. Asegúrate de que el servidor esté en ejecución.")

except requests.exceptions.Timeout:
    print("Error: La solicitud al servidor ha excedido el tiempo de espera.")

except requests.exceptions.HTTPError as http_err:
    print(f"Error HTTP: {http_err}")

except Exception as err:
    print(f"Error inesperado: {err}")
