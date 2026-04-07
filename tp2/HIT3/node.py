"""
HIT3 - Nodo del sistema distribuido con elección de líder (Algoritmo Bully).

Cada nodo puede ser LEADER o FOLLOWER.
- El LEADER coordina la asignación de tareas a los workers disponibles.
- Los FOLLOWERS reenvían tareas al líder y monitorean su salud via heartbeat.
- Si el líder cae, se inicia una elección Bully automáticamente.
"""

import json
import logging
import os
import threading
import time

import requests
from flask import Flask, jsonify, request

# Configuración del nodo (via variables de entorno)
NODE_ID = int(os.environ.get("NODE_ID", 1))
NODE_HOST = os.environ.get("NODE_HOST", "localhost")
NODE_PORT = int(os.environ.get("NODE_PORT", 7001))

# PEERS_JSON = '[{"id":2,"host":"node2","port":7002},{"id":3,"host":"node3","port":7003}]'
PEERS_JSON = os.environ.get("PEERS_JSON", "[]")

HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", 2.0))
HEARTBEAT_TIMEOUT = float(os.environ.get("HEARTBEAT_TIMEOUT", 5.0))
ELECTION_TIMEOUT = float(os.environ.get("ELECTION_TIMEOUT", 3.0))

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format=f"%(asctime)s [NODO-{NODE_ID}] %(message)s",
)

# Estado del nodo
peers: list[dict] = json.loads(PEERS_JSON)
leader_id: int | None = None
leader_lock = threading.Lock()
election_in_progress = threading.Event()
coordinator_received = threading.Event()

stats = {
    "tareas_procesadas": 0,
    "tareas_asignadas": 0,
    "elecciones_participadas": 0,
    "tiempo_ultima_eleccion_ms": 0,
}
stats_lock = threading.Lock()

# Cola de tareas pendientes que se redistribuyen si el líder cae
tareas_pendientes: list[dict] = []
tareas_lock = threading.Lock()

# Round-robin index para asignar tareas
rr_index = 0
rr_lock = threading.Lock()


def soy_lider() -> bool:
    with leader_lock:
        return leader_id == NODE_ID


def set_leader(new_leader: int | None):
    global leader_id
    with leader_lock:
        leader_id = new_leader


def get_leader() -> int | None:
    with leader_lock:
        return leader_id


def get_peer(node_id: int) -> dict | None:
    for p in peers:
        if p["id"] == node_id:
            return p
    return None


def peer_url(peer: dict, path: str) -> str:
    return f"http://{peer['host']}:{peer['port']}{path}"


def self_info() -> dict:
    return {"id": NODE_ID, "host": NODE_HOST, "port": NODE_PORT}


def all_node_ids() -> list[int]:
    return sorted([NODE_ID] + [p["id"] for p in peers])


# Ejecución local de tareas (misma lógica que servidorTarea.py)
def ejecutar_tarea(operacion: str, valores: list) -> dict:
    if operacion == "suma":
        resultado = sum(valores)
    elif operacion == "resta":
        resultado = valores[0] - sum(valores[1:])
    elif operacion == "multiplicacion":
        resultado = 1
        for v in valores:
            resultado *= v
    elif operacion == "division":
        resultado = valores[0]
        for v in valores[1:]:
            if v == 0:
                return {"error": "División por cero no permitida"}
            resultado /= v
    else:
        return {"error": f"Operación no soportada: {operacion}"}

    return {"resultado": resultado, "operacion": operacion, "valores": valores}


# Algoritmo Bully - Elección de líder
def iniciar_eleccion():
    """
    Algoritmo Bully:
    1. Enviar ELECTION a todos los nodos con ID mayor.
    2. Si alguno responde OK, esperar a que ese nodo se declare COORDINATOR.
    3. Si ninguno responde, declararse COORDINATOR.
    """
    if election_in_progress.is_set():
        logging.info("Elección ya en progreso, ignorando.")
        return

    election_in_progress.set()
    coordinator_received.clear()
    inicio_eleccion = time.time()

    with stats_lock:
        stats["elecciones_participadas"] += 1

    logging.info("=== INICIANDO ELECCIÓN BULLY ===")

    nodos_mayores = [p for p in peers if p["id"] > NODE_ID]

    if not nodos_mayores:
        # Soy el nodo con mayor ID → me declaro coordinador
        logging.info("No hay nodos con ID mayor. Me declaro COORDINATOR.")

        declarar_coordinador(inicio_eleccion)

        election_in_progress.clear()

        return

    # Enviar ELECTION a nodos con ID mayor
    alguno_respondio = False
    for peer in nodos_mayores:
        try:
            logging.info(f"Enviando ELECTION a Nodo-{peer['id']}")

            resp = requests.post(
                peer_url(peer, "/election"),
                json={"from_id": NODE_ID},
                timeout=ELECTION_TIMEOUT,
            )

            if resp.status_code == 200:
                logging.info(f"Nodo-{peer['id']} respondió OK a mi ELECTION.")

                alguno_respondio = True
        except Exception:
            logging.info(f"Nodo-{peer['id']} no respondió al ELECTION (posiblemente caído).")

    if not alguno_respondio:
        # Ningún nodo mayor respondió → me declaro coordinador
        logging.info("Ningún nodo mayor respondió. Me declaro COORDINATOR.")
        declarar_coordinador(inicio_eleccion)
    else:
        # Esperar a recibir COORDINATOR de algún nodo mayor
        logging.info(f"Esperando mensaje COORDINATOR (timeout={ELECTION_TIMEOUT * 2}s)...")
        if not coordinator_received.wait(timeout=ELECTION_TIMEOUT * 2):
            # Timeout esperando coordinador → iniciar nueva elección
            logging.info("Timeout esperando COORDINATOR. Re-iniciando elección.")
            election_in_progress.clear()
            iniciar_eleccion()
            return

    election_in_progress.clear()


def declarar_coordinador(inicio_eleccion: float):
    set_leader(NODE_ID)
    tiempo_ms = (time.time() - inicio_eleccion) * 1000

    with stats_lock:
        stats["tiempo_ultima_eleccion_ms"] = round(tiempo_ms, 2)

    logging.info(f"*** SOY EL NUEVO LÍDER (ID={NODE_ID}) *** Tiempo de elección: {tiempo_ms:.2f}ms")

    # Notificar a todos los peers
    for peer in peers:
        try:
            requests.post(
                peer_url(peer, "/coordinator"),
                json={"leader_id": NODE_ID},
                timeout=2,
            )
            logging.info(f"COORDINATOR enviado a Nodo-{peer['id']}")
        except Exception:
            logging.info(f"No se pudo notificar COORDINATOR a Nodo-{peer['id']} (posiblemente caído).")

    # Redistribuir tareas pendientes
    redistribuir_tareas()


def redistribuir_tareas():
    """Redistribuye tareas que estaban pendientes cuando el líder anterior cayó."""
    with tareas_lock:
        pendientes = list(tareas_pendientes)
        tareas_pendientes.clear()

    if pendientes:
        logging.info(f"Redistribuyendo {len(pendientes)} tareas pendientes...")
        for tarea in pendientes:
            threading.Thread(
                target=procesar_tarea_como_lider,
                args=(tarea["operation"], tarea["values"]),
                daemon=True,
            ).start()


# Heartbeat - Monitoreo del líder
def heartbeat_loop():
    """
    Loop que corre en followers para verificar que el líder está vivo.
    Si el heartbeat falla, inicia una elección.
    """
    time.sleep(3)  # Esperar a que el sistema se estabilice

    while True:
        time.sleep(HEARTBEAT_INTERVAL)

        current_leader = get_leader()

        if current_leader is None:
            logging.info("No hay líder conocido. Iniciando elección.")

            threading.Thread(target=iniciar_eleccion, daemon=True).start()

            time.sleep(ELECTION_TIMEOUT * 3)

            continue

        if current_leader == NODE_ID:
            continue  # Soy el líder, no necesito hacer heartbeat

        peer = get_peer(current_leader)
        if peer is None:
            continue

        try:
            resp = requests.get(
                peer_url(peer, "/health"),
                timeout=HEARTBEAT_TIMEOUT,
            )

            if resp.status_code == 200:
                continue  # Líder vivo

        except Exception:
            pass

        logging.info(f"¡LÍDER ({peer['host']}) NO RESPONDE! Iniciando elección...")

        set_leader(None)

        threading.Thread(target=iniciar_eleccion, daemon=True).start()

        time.sleep(ELECTION_TIMEOUT * 3)  # Dar tiempo a la elección


# Procesamiento de tareas
def obtener_nodos_disponibles() -> list[dict]:
    """Retorna lista de nodos (peers + yo) que están vivos."""
    disponibles = [{"id": NODE_ID, "host": NODE_HOST, "port": NODE_PORT}]
    for peer in peers:
        try:
            resp = requests.get(peer_url(peer, "/health"), timeout=1)
            if resp.status_code == 200:
                disponibles.append(peer)
        except Exception:
            pass
    return disponibles


def asignar_nodo_worker(disponibles: list[dict]) -> dict:
    """Round-robin entre nodos disponibles."""
    global rr_index
    with rr_lock:
        nodo = disponibles[rr_index % len(disponibles)]
        rr_index += 1
    return nodo


def procesar_tarea_como_lider(operacion: str, valores: list) -> dict:
    """El líder asigna la tarea a un worker disponible."""
    disponibles = obtener_nodos_disponibles()
    worker = asignar_nodo_worker(disponibles)

    logging.info(f"[LÍDER] Asignando tarea '{operacion}' a {worker['host']}")

    with stats_lock:
        stats["tareas_asignadas"] += 1

    if worker["id"] == NODE_ID:
        # Ejecutar localmente
        resultado = ejecutar_tarea(operacion, valores)
        with stats_lock:
            stats["tareas_procesadas"] += 1
        logging.info(f"Tarea terminada: {operacion} {valores} -> {resultado}")
        return {"result": resultado, "worker_id": NODE_ID, "leader_id": NODE_ID}

    # Enviar al worker remoto
    try:
        resp = requests.post(
            peer_url(worker, "/execute-task"),
            json={"operation": operacion, "values": valores},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        data["leader_id"] = NODE_ID
        return data
    except Exception as e:
        logging.error(f"Error asignando tarea a Nodo-{worker['id']}: {e}")
        # Fallback: ejecutar localmente
        resultado = ejecutar_tarea(operacion, valores)
        with stats_lock:
            stats["tareas_procesadas"] += 1
        return {"result": resultado, "worker_id": NODE_ID, "leader_id": NODE_ID}


# Endpoints Flask
@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "node_id": NODE_ID,
            "role": "LEADER" if soy_lider() else "FOLLOWER",
            "leader_id": get_leader(),
        }
    )


@app.route("/election", methods=["POST"])
def recibir_election():
    """
    Recibe un mensaje ELECTION de un nodo con ID menor.
    Responde OK e inicia su propia elección.
    """
    data = request.get_json()
    from_id = data.get("from_id", 0)

    logging.info(f"Recibido ELECTION de Nodo-{from_id}. Respondiendo OK.")

    # Iniciar mi propia elección en background
    threading.Thread(target=iniciar_eleccion, daemon=True).start()

    return jsonify({"status": "OK", "from_id": NODE_ID}), 200


@app.route("/coordinator", methods=["POST"])
def recibir_coordinator():
    """Recibe el anuncio de un nuevo coordinador."""
    data = request.get_json()
    new_leader = data.get("leader_id")

    logging.info(f"*** Nodo-{new_leader} es el nuevo LÍDER ***")

    set_leader(new_leader)
    coordinator_received.set()

    return jsonify({"status": "acknowledged"}), 200


@app.route("/task", methods=["POST"])
def recibir_tarea():
    """
    Endpoint principal para recibir tareas (desde el Load Balancer o cliente).
    - Si soy líder: asigno la tarea a un worker.
    - Si soy follower: reenvío al líder.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON inválido o no proporcionado."}), 400

    operacion = data.get("operation")
    valores = data.get("values")

    if not operacion or valores is None:
        return jsonify({"error": "Faltan 'operation' o 'values'."}), 400

    logging.info(f"Tarea recibida: {operacion} {valores}")

    if soy_lider():
        resultado = procesar_tarea_como_lider(operacion, valores)
        return jsonify(resultado)

    # Soy follower → reenviar al líder
    current_leader = get_leader()

    if current_leader is None:
        # No hay líder, guardar como pendiente e iniciar elección
        with tareas_lock:
            tareas_pendientes.append({"operation": operacion, "values": valores})

        threading.Thread(target=iniciar_eleccion, daemon=True).start()

        return jsonify({"error": "No hay líder activo. Elección en progreso."}), 503

    peer = get_peer(current_leader)
    if peer is None:
        return jsonify({"error": "Líder no encontrado en peers."}), 500

    try:
        logging.info(f"Reenviando tarea al líder ({peer['host']})")
        resp = requests.post(
            peer_url(peer, "/task"),
            json=data,
            timeout=30,
        )
        return jsonify(resp.json()), resp.status_code
    except Exception:
        logging.error(f"Líder (Nodo-{current_leader}) no accesible. Iniciando elección.")
        set_leader(None)
        with tareas_lock:
            tareas_pendientes.append({"operation": operacion, "values": valores})
        threading.Thread(target=iniciar_eleccion, daemon=True).start()
        return jsonify({"error": "Líder caído. Elección en progreso."}), 503


@app.route("/execute-task", methods=["POST"])
def ejecutar_tarea_asignada():
    """
    Endpoint para que el líder asigne una tarea directamente a este nodo.
    """
    data = request.get_json()
    operacion = data.get("operation")
    valores = data.get("values")

    logging.info(f"Ejecutando tarea asignada: {operacion} {valores}")

    resultado = ejecutar_tarea(operacion, valores)

    with stats_lock:
        stats["tareas_procesadas"] += 1

    logging.info(f"Tarea terminada: {operacion} {valores} -> {resultado}")

    return jsonify({"result": resultado, "worker_id": NODE_ID})


@app.route("/status")
def status():
    """Estado completo del nodo para monitoreo."""
    with stats_lock:
        stats_copy = dict(stats)

    nodos_vivos = []
    for peer in peers:
        try:
            resp = requests.get(peer_url(peer, "/health"), timeout=1)
            if resp.status_code == 200:
                nodos_vivos.append(peer["id"])
        except Exception:
            pass

    return jsonify(
        {
            "node_id": NODE_ID,
            "role": "LEADER" if soy_lider() else "FOLLOWER",
            "leader_id": get_leader(),
            "nodos_vivos": sorted(nodos_vivos + [NODE_ID]),
            "nodos_totales": sorted(all_node_ids()),
            "stats": stats_copy,
        }
    )


# Inicio del nodo
def startup():
    logging.info(f"Nodo-{NODE_ID} iniciando en {NODE_HOST}:{NODE_PORT}")
    logging.info(f"Peers: {peers}")

    # Esperar a que los peers estén listos
    time.sleep(2)

    # Iniciar elección para determinar el líder inicial
    logging.info("Iniciando elección inicial...")
    iniciar_eleccion()

    # Iniciar heartbeat loop en background
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()
    logging.info("Heartbeat monitor iniciado.")


if __name__ == "__main__":
    # Lanzar startup en background para no bloquear Flask
    threading.Thread(target=startup, daemon=True).start()

    app.run(host="0.0.0.0", port=NODE_PORT, threaded=True)
