import argparse
import json
import os

import requests

REMOTE_URL = "http://3.144.148.19:8080/task"

LOCAL_URL = "http://localhost:8080/task"

parser = argparse.ArgumentParser(description="Cliente HIT3 - Envía tareas al Load Balancer.")

parser.add_argument(
    "--operacion",
    type=str,
    required=True,
    choices=["suma", "resta", "multiplicacion", "division"],
    help="Operación a ejecutar.",
)

parser.add_argument(
    "--valores",
    type=float,
    nargs="+",
    required=True,
    help="Números sobre los que operar. Ej: --valores 10 25 7",
)

parser.add_argument(
    "--remote",
    action="store_true",
    help="Conectar al servidor remoto en AWS.",
)

args = parser.parse_args()

SERVER_URL = REMOTE_URL if args.remote else os.environ.get("SERVER_URL", LOCAL_URL)

if len(args.valores) < 2:
    print("Error: se requieren al menos 2 valores.")
    exit()

PAYLOAD = {
    "operation": args.operacion,
    "values": args.valores,
}

try:
    respuesta = requests.post(SERVER_URL, json=PAYLOAD, timeout=60)
    respuesta.raise_for_status()

    resultado = respuesta.json()
    print(f"Resultado: {json.dumps(resultado, indent=2, ensure_ascii=False)}")

except requests.exceptions.ConnectionError:
    print("Error: No se pudo conectar al servidor.")

except requests.exceptions.Timeout:
    print("Error: Timeout.")

except requests.exceptions.HTTPError as http_err:
    print(f"Error HTTP: {http_err}")

except Exception as err:
    print(f"Error inesperado: {err}")
