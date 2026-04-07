import argparse
import json
import os

import requests

REMOTE_URL = "http://3.144.148.19:6000/task"
LOCAL_URL = "http://localhost:6000/task"

parser = argparse.ArgumentParser(description="Cliente para ejecutar operaciones matematicas en el servidor.")

parser.add_argument(
    "--operacion",
    type=str,
    required=True,
    choices=["suma", "resta", "multiplicacion", "division"],
    help="Operacion a ejecutar.",
)

parser.add_argument(
    "--valores",
    type=float,
    nargs="+",
    required=True,
    help="Numeros sobre los que operar. Ej: --valores 10 25 7",
)

parser.add_argument("--remote", action="store_true", help="Conectar al servidor remoto en AWS.")

parser.add_argument(
    "--lamport",
    type=int,
    default=0,
    help="Timestamp de Lamport opcional para enviar con la solicitud.",
)

args = parser.parse_args()

SERVER_URL = REMOTE_URL if args.remote else os.environ.get("SERVER_URL", LOCAL_URL)

if len(args.valores) < 2:
    print("Error: se requieren al menos 2 valores para realizar la operacion.")
    exit()

PAYLOAD = {
    "operation": args.operacion,
    "values": args.valores,
    "lamport_ts": args.lamport,
}

print("Enviando tarea...")

try:
    respuesta = requests.post(SERVER_URL, json=PAYLOAD, timeout=120)
    respuesta.raise_for_status()

    data = respuesta.json()

    resultado = data.get("result")

    print(f"Resultado: {json.dumps(resultado, indent=2, ensure_ascii=False)}")
    print(f"Lamport TS servidor: {data.get('lamport_ts')}")
    print(f"Worker que proceso la tarea: {data.get('worker_id')}")

except requests.exceptions.ConnectionError:
    print("Error: No se pudo conectar al servidor.")

except requests.exceptions.Timeout:
    print("Error: Timeout al esperar respuesta del servidor.")

except requests.exceptions.HTTPError as http_err:
    print(f"Error HTTP: {http_err}")

except Exception as err:
    print(f"Error inesperado: {err}")
