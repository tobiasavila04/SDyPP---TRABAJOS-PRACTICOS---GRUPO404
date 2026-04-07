import atexit
import heapq
import logging
import os
import socket
import subprocess
import threading
import time
import uuid

import requests
from flask import Flask, jsonify, request

IMAGE = os.environ.get("TASK_IMAGE", "tobiasavila142/servicio-tareas:latest")
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", 4))
TASK_DELAY = float(os.environ.get("TASK_DELAY", 0))

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SERVIDOR] %(message)s")


# ---------------------------------------------------------------------------
# Reloj de Lamport del servidor
# ---------------------------------------------------------------------------
class RelojLamport:
    def __init__(self):
        self._lock = threading.Lock()
        self._valor = 0

    def incrementar(self) -> int:
        with self._lock:
            self._valor += 1
            return self._valor

    def actualizar(self, ts_recibido: int) -> int:
        with self._lock:
            self._valor = max(self._valor, ts_recibido) + 1
            return self._valor

    @property
    def valor(self) -> int:
        with self._lock:
            return self._valor


reloj = RelojLamport()


# ---------------------------------------------------------------------------
# Cola de tareas con exclusion mutua (min-heap ordenado por Lamport TS)
# ---------------------------------------------------------------------------
class ColaTareas:
    """
    Cola con prioridad basada en timestamps de Lamport.
    Usa un mutex (threading.Lock) para garantizar exclusion mutua:
    - Solo un hilo puede encolar/desencolar a la vez.
    - Cuando no hay workers disponibles, las tareas esperan en la cola.
    """

    def __init__(self):
        self._lock = threading.Lock()

        self._heap: list[tuple[int, str, dict]] = []

        self._condicion = threading.Condition(self._lock)

    def encolar(self, lamport_ts: int, task_id: str, tarea: dict):
        with self._condicion:  # Toma el lock para modificar la cola
            heapq.heappush(self._heap, (lamport_ts, task_id, tarea))

            logging.info(
                "[COLA] Tarea '%s' encolada con Lamport TS=%d. Tamanio cola: %d",
                task_id,
                lamport_ts,
                len(self._heap),
            )

            self._condicion.notify()  # Despierta a un worker que esté esperando por tareas

    def desencolar(self) -> tuple[int, str, dict]:
        with self._condicion:
            while len(self._heap) == 0:
                self._condicion.wait()

            item = heapq.heappop(self._heap)

            logging.info(
                "[COLA] Tarea '%s' desencolada (Lamport TS=%d). Tamanio cola: %d",
                item[1],
                item[0],
                len(self._heap),
            )

            return item

    @property
    def tamanio(self) -> int:
        with self._lock:
            return len(self._heap)


cola = ColaTareas()

# Resultados pendientes (cada tarea espera su resultado via un Event)
resultados: dict[str, dict] = {}
eventos: dict[str, threading.Event] = {}
resultados_lock = threading.Lock()


# Gestion de containers pre-levantados
def encontrar_puerto_libre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def esperar_servicio(puerto, reintentos: int = 30, espera: float = 1.0):
    url = f"http://localhost:{puerto}/health"
    for intento in range(1, reintentos + 1):
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                logging.info("Servicio en puerto %d listo.", puerto)
                return
        except requests.exceptions.ConnectionError:
            pass
        logging.info(
            "Esperando container en :%d - intento %d/%d",
            puerto,
            intento,
            reintentos,
        )
        time.sleep(espera)
    raise TimeoutError(f"Servicio en puerto {puerto} no respondio tras {reintentos} intentos.")


def levantar_containers(n: int) -> list[dict]:
    """
    Levanta N containers de la imagen de tareas al inicio.
    Retorna una lista de dicts con {nombre, puerto} para cada worker.
    """
    workers_info = []
    for i in range(1, n + 1):
        nombre = f"worker-{i}"
        puerto = encontrar_puerto_libre()

        # Limpiar container previo con ese nombre si existe
        subprocess.run(["docker", "rm", "-f", nombre], capture_output=True)

        logging.info("Levantando container '%s' en puerto %d...", nombre, puerto)
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "-p",
                f"{puerto}:8080",
                "--name",
                nombre,
                IMAGE,
            ],
            check=True,
            capture_output=True,
        )
        workers_info.append({"nombre": nombre, "puerto": puerto})

    # Esperar a que todos los containers esten listos
    for info in workers_info:
        esperar_servicio(info["puerto"])

    logging.info("%d containers levantados y listos.", n)

    return workers_info


def eliminar_containers(workers_info: list[dict]):
    logging.info("Eliminando containers de workers...")

    for info in workers_info:
        subprocess.run(["docker", "stop", info["nombre"]], capture_output=True)

        subprocess.run(["docker", "rm", info["nombre"]], capture_output=True)


# Worker: hilo que toma tareas de la cola y las envia a SU container
def worker(worker_id: int, puerto: int):
    url_tarea = f"http://localhost:{puerto}/run"

    logging.info("[WORKER-%d] Iniciado, usando puerto %d.", worker_id, puerto)

    while True:
        lamport_ts, task_id, tarea = cola.desencolar()

        logging.info(
            "[WORKER-%d] Procesando tarea '%s' (Lamport TS=%d)",
            worker_id,
            task_id,
            lamport_ts,
        )

        try:
            if TASK_DELAY > 0:
                time.sleep(TASK_DELAY)

            resp = requests.post(
                url_tarea,
                json={"operation": tarea["operation"], "values": tarea["values"]},
                timeout=60,
            )

            resp.raise_for_status()

            ts_respuesta = reloj.incrementar()

            resultado = {
                "result": resp.json(),
                "lamport_ts": ts_respuesta,
                "worker_id": worker_id,
            }

            logging.info(
                "[WORKER-%d] Tarea '%s' completada. Lamport TS=%d",
                worker_id,
                task_id,
                ts_respuesta,
            )

        except Exception as e:
            logging.error("[WORKER-%d] Error en tarea '%s': %s", worker_id, task_id, e)

            resultado = {
                "error": f"Error: {str(e)}",
                "lamport_ts": reloj.incrementar(),
            }

        # Publicar resultado y despertar al hilo HTTP que espera
        with resultados_lock:
            resultados[task_id] = resultado

        eventos[task_id].set()


# Iniciar pool de workers
def iniciar_workers(workers_info: list[dict]):

    for i, info in enumerate(workers_info, start=1):
        t = threading.Thread(target=worker, args=(i, info["puerto"]), daemon=True)

        t.start()

    logging.info("Pool de %d worker threads iniciado.", len(workers_info))


# Endpoints
@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "max_workers": MAX_WORKERS,
            "cola_pendiente": cola.tamanio,
            "lamport_ts": reloj.valor,
        }
    )


@app.route("/task", methods=["POST"])
def recibir_tarea():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON invalido o no proporcionado."}), 400

    operacion = data.get("operation")
    valores = data.get("values")
    ts_cliente = data.get("lamport_ts", 0)

    if not operacion or valores is None:
        return jsonify({"error": "Faltan 'operation' o 'values' en el JSON."}), 400

    # Si el cliente manda un lamport_ts, se actualiza; si no, solo incrementa
    if ts_cliente > 0:
        ts_servidor = reloj.actualizar(ts_cliente)
    else:
        ts_servidor = reloj.incrementar()

    logging.info(
        "Tarea recibida - op: %s, valores: %s, lamport_cliente: %d, lamport_servidor: %d",
        operacion,
        valores,
        ts_cliente,
        ts_servidor,
    )

    # Crear evento para esperar resultado
    task_id = uuid.uuid4().hex[:12]  #
    evento = threading.Event()  # Aca se crea el objeto event
    eventos[task_id] = evento

    # Encolar con el timestamp de Lamport del servidor
    cola.encolar(ts_servidor, task_id, {"operation": operacion, "values": valores})

    # Esperar a que un worker complete la tarea
    evento.wait(timeout=120)

    with resultados_lock:
        resultado = resultados.pop(task_id, None)

    eventos.pop(task_id, None)

    if resultado is None:
        return jsonify({"error": "Timeout esperando resultado."}), 504

    if "error" in resultado:
        return jsonify(resultado), 500

    return jsonify(resultado)


if __name__ == "__main__":
    workers_info = levantar_containers(MAX_WORKERS)

    # Cuando el servidor se apague, se eliminan los containers de los workers
    atexit.register(eliminar_containers, workers_info)

    iniciar_workers(workers_info)

    logging.info("Servidor iniciando con %d workers.", MAX_WORKERS)

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 6000)), threaded=True)
