import base64
import json
import os
import time

import cv2
import numpy as np
import pika
import redis as redis_client
from prometheus_client import Counter, Histogram, start_http_server

RABBIT_HOST = os.getenv("RABBIT_HOST", "rabbitmq")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
CANTIDAD_CHUNKS = int(os.getenv("CANTIDAD_CHUNKS", "4"))

chunks_received = Counter("chunks_received_total", "Chunks de resultado recibidos")
jobs_completed = Counter("jobs_completed_total", "Jobs completados (imagen ensamblada)")
join_duration = Histogram("join_duration_seconds", "Tiempo desde primer chunk hasta imagen final")

print("--- Iniciando Joiner ---")
start_http_server(8001)

redis = redis_client.Redis(host=REDIS_HOST, port=6379, decode_responses=False)


def connect_to_rabbit(host):
    max_retries = 5
    base_delay = 1
    max_delay = 30
    for attempt in range(max_retries):
        try:
            print(f" [*] Intentando conectar a RabbitMQ en {host} (Intento {attempt+1}/{max_retries})")
            connection = pika.BlockingConnection(pika.ConnectionParameters(host))
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            delay = min(base_delay * (2 ** attempt), max_delay)
            print(f" [X] Error conectando: {e}. Reintentando en {delay}s...")
            time.sleep(delay)
    print(" [X] Falla crítica: No se pudo conectar a RabbitMQ después de varios reintentos.")
    exit(1)


connection = connect_to_rabbit(RABBIT_HOST)
channel = connection.channel()

channel.exchange_declare(exchange='resultados_exchange', exchange_type='fanout')

result = channel.queue_declare(queue='', exclusive=True)
queue_name = result.method.queue
channel.queue_bind(exchange='resultados_exchange', queue=queue_name)

pedazos_recibidos = {}
tiempo_inicio = None


def callback(ch, method, properties, body):
    global tiempo_inicio

    if tiempo_inicio is None:
        tiempo_inicio = time.time()

    datos = json.loads(body.decode())
    chunk_id = datos["chunk_id"]
    job_id = datos.get("job_id")
    total_chunks = datos.get("total_chunks", CANTIDAD_CHUNKS)
    img_b64 = datos["image_data"]

    print(f" [v] Recibido chunk procesado {chunk_id}")

    img_bytes = base64.b64decode(img_b64)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    pedazo = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)

    pedazos_recibidos[chunk_id] = pedazo
    ch.basic_ack(delivery_tag=method.delivery_tag)
    chunks_received.inc()

    if len(pedazos_recibidos) == total_chunks:
        print("\n [*] ¡Todos los pedazos recibidos! Unificando...")

        pedazos_ordenados = [pedazos_recibidos[i] for i in range(total_chunks)]
        imagen_final = np.vstack(pedazos_ordenados)

        tiempo_total = time.time() - tiempo_inicio
        join_duration.observe(tiempo_total)
        jobs_completed.inc()

        cv2.imwrite("resultado_distribuido.jpg", imagen_final)
        print(" [V] ¡Éxito! Imagen guardada como 'resultado_distribuido.jpg'")
        print(f" [*] TIEMPO TOTAL DISTRIBUIDO: {tiempo_total:.4f} segundos")

        if job_id:
            _, result_buf = cv2.imencode(".jpg", imagen_final)
            result_b64 = base64.b64encode(result_buf).decode("utf-8")
            redis.setex(f"result:{job_id}", 3600, result_b64)
            print(f" [*] Resultado guardado en Redis con key result:{job_id}")

        channel.stop_consuming()


channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

print(" [*] Esperando pedazos procesados...")
channel.start_consuming()
