import logging
import os
import socket
import subprocess
import time
import uuid  # Lo usamos para darle un nombre único a cada container efímero y evitar colisiones

import requests
from flask import Flask, jsonify, request

IMAGE = os.environ.get("TASK_IMAGE", "tobiasavila142/servicio-tareas:latest")

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SERVIDOR] %(message)s")


def encontrar_puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def esperar_servicio(puerto, reintentos: int = 20, espera: float = 1.0):
    url = f"http://localhost:{puerto}/health"

    for intento in range(1, reintentos + 1):
        try:
            respuesta = requests.get(url, timeout=2)

            if respuesta.status_code == 200:
                logging.info(f"Servicio en puerto {puerto} está listo.")
                return

        except requests.exceptions.ConnectionError:
            pass

        logging.info(f"Esperando container en :{puerto} — intento {intento}/{reintentos}")

        time.sleep(espera)

    raise TimeoutError(f"El servicio en puerto {puerto} no respondió después de {reintentos} intentos.")


def elimar_container(nombre_container: str):
    """
    capture_output=True suprime la salida en la consola.
    No lanzamos excepción si falla porque el container puede ya estar muerto.
    """
    subprocess.run(["docker", "stop", nombre_container], capture_output=True)

    subprocess.run(["docker", "rm", nombre_container], capture_output=True)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/task", methods=["POST"])
def ejecutarServidorTarea():

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido o no proporcionado."}), 400

    operacion = data.get("operation")
    valores = data.get("values")

    if not operacion or valores is None:
        return jsonify({"error": "Faltan 'operaciones' o 'valores' en el JSON."}), 400

    logging.info(f"Nueva tarea - operacion: {operacion}, valores: {valores}")

    nombre_container = f"task-{uuid.uuid4()}"
    puerto_host = encontrar_puerto_libre()

    try:
        logging.info(f"Creando container '{nombre_container}' en puerto {puerto_host}...")
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "-p",
                f"{puerto_host}:8080",
                "--name",
                nombre_container,
                IMAGE,
            ],
            check=True,
            capture_output=True,
        )

        esperar_servicio(puerto_host)

        url_tarea = f"http://localhost:{puerto_host}/run"
        logging.info(f"Enviando tarea al container '{nombre_container}' en {url_tarea}...")

        respuesta = requests.post(url_tarea, json={"operation": operacion, "values": valores}, timeout=60)

        respuesta.raise_for_status()

        resultado = respuesta.json()

        logging.info(f"Resultado: {resultado}")
        return jsonify({"result": resultado})

    except subprocess.CalledProcessError as e:
        logging.error(f"Error al crear el container: {e.stderr.decode()}")
        return jsonify({"error": "Error al crear el container."}), 500

    except TimeoutError as e:
        logging.error(str(e))
        return jsonify({"error": "El servicio del container no respondió a tiempo."}), 504

    except Exception as e:
        logging.error(f"Error inesperado: {str(e)}")
        return jsonify({"error": "Error inesperado al ejecutar la tarea."}), 500

    finally:
        logging.info(f"Eliminando container '{nombre_container}'")
        elimar_container(nombre_container)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5005)))
