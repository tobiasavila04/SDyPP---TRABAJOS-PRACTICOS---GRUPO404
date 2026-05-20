import base64
import json
import os
import time
import uuid

import cv2
import numpy as np
import pika
from prometheus_client import Counter, Histogram, start_http_server

RABBIT_HOST = os.getenv("RABBIT_HOST", "rabbitmq")
nombre_imagen = os.getenv("IMAGEN", "imagen_prueba.jpg")
CANTIDAD_CHUNKS = int(os.getenv("CANTIDAD_CHUNKS", "4"))
JOB_ID = os.getenv("JOB_ID", str(uuid.uuid4()))

chunks_published = Counter("chunks_published_total", "Total chunks enviados a la cola")
split_duration = Histogram("split_duration_seconds", "Tiempo de fragmentación de imagen")

print("--- Iniciando Splitter ---")
start_http_server(8000)

if not os.path.exists(nombre_imagen):
    print(f"[X] Error: No se encontró '{nombre_imagen}'.")
    exit()


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

channel.exchange_declare(exchange='dlx_tareas', exchange_type='direct')
channel.queue_declare(queue='tareas_sobel_dlq', durable=True)
channel.queue_bind(exchange='dlx_tareas', queue='tareas_sobel_dlq', routing_key='tareas_sobel_dlq')

channel.queue_declare(queue="tareas_sobel", durable=True, arguments={
    'x-dead-letter-exchange': 'dlx_tareas',
    'x-dead-letter-routing-key': 'tareas_sobel_dlq'
})

imagen = cv2.imread(nombre_imagen, cv2.IMREAD_GRAYSCALE)
alto, ancho = imagen.shape
alto_chunk = alto // CANTIDAD_CHUNKS

print(f"[*] Job {JOB_ID} — Imagen: {ancho}x{alto}. Cortando en {CANTIDAD_CHUNKS} pedazos...")

start_time = time.time()

with split_duration.time():
    for i in range(CANTIDAD_CHUNKS):
        y_inicio = i * alto_chunk
        y_fin = alto if i == CANTIDAD_CHUNKS - 1 else (i + 1) * alto_chunk

        pedazo = imagen[y_inicio:y_fin, :]

        _, buffer = cv2.imencode(".jpg", pedazo)
        img_b64 = base64.b64encode(buffer).decode("utf-8")

        mensaje = {
            "job_id": JOB_ID,
            "chunk_id": i,
            "total_chunks": CANTIDAD_CHUNKS,
            "image_data": img_b64,
            "start_time": start_time,
        }

        channel.basic_publish(exchange="", routing_key="tareas_sobel", body=json.dumps(mensaje))
        chunks_published.inc()
        print(f" [x] Enviado Chunk {i}")

connection.close()
print(" [*] Todos los pedazos fueron enviados a la cola.")
