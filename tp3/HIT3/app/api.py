import base64
import json
import os
import uuid

import pika
import redis as redis_client
from flask import Flask, jsonify, request

app = Flask(__name__)

RABBIT_HOST = os.getenv("RABBIT_HOST", "rabbitmq")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
CANTIDAD_CHUNKS = int(os.getenv("CANTIDAD_CHUNKS", "4"))

redis = redis_client.Redis(host=REDIS_HOST, port=6379, decode_responses=True)


def get_rabbit_channel():
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
    channel = connection.channel()
    channel.exchange_declare(exchange='dlx_tareas', exchange_type='direct')
    channel.queue_declare(queue='tareas_sobel_dlq', durable=True)
    channel.queue_bind(exchange='dlx_tareas', queue='tareas_sobel_dlq', routing_key='tareas_sobel_dlq')
    channel.queue_declare(queue="tareas_sobel", durable=True, arguments={
        'x-dead-letter-exchange': 'dlx_tareas',
        'x-dead-letter-routing-key': 'tareas_sobel_dlq'
    })
    return connection, channel


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "sobel-api"})


@app.post("/process")
def process():
    """Acepta imagen en base64 y la encola para procesamiento Sobel distribuido."""
    data = request.get_json(force=True)
    if not data or "image_data" not in data:
        return jsonify({"error": "Se requiere 'image_data' en base64"}), 400

    job_id = str(uuid.uuid4())
    img_b64 = data["image_data"]
    size_label = data.get("size_label", "unknown")

    try:
        img_bytes = base64.b64decode(img_b64)
    except Exception:
        return jsonify({"error": "image_data no es base64 válido"}), 400

    import cv2
    import numpy as np

    np_arr = np.frombuffer(img_bytes, np.uint8)
    imagen = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
    if imagen is None:
        return jsonify({"error": "No se pudo decodificar la imagen"}), 400

    alto, ancho = imagen.shape
    alto_chunk = alto // CANTIDAD_CHUNKS

    try:
        connection, channel = get_rabbit_channel()
    except Exception as e:
        return jsonify({"error": f"No se pudo conectar a RabbitMQ: {e}"}), 503

    import time
    start_time = time.time()

    for i in range(CANTIDAD_CHUNKS):
        y_inicio = i * alto_chunk
        y_fin = alto if i == CANTIDAD_CHUNKS - 1 else (i + 1) * alto_chunk
        pedazo = imagen[y_inicio:y_fin, :]

        _, buffer = cv2.imencode(".jpg", pedazo)
        chunk_b64 = base64.b64encode(buffer).decode("utf-8")

        mensaje = {
            "job_id": job_id,
            "chunk_id": i,
            "total_chunks": CANTIDAD_CHUNKS,
            "image_data": chunk_b64,
            "start_time": start_time,
            "size_label": size_label,
        }
        channel.basic_publish(exchange="", routing_key="tareas_sobel", body=json.dumps(mensaje))

    connection.close()

    redis.setex(f"status:{job_id}", 3600, "processing")
    return jsonify({"job_id": job_id, "chunks": CANTIDAD_CHUNKS, "size_label": size_label}), 202


@app.get("/result/<job_id>")
def get_result(job_id):
    """Consulta el resultado de un job en Redis."""
    result = redis.get(f"result:{job_id}")
    if result is None:
        status = redis.get(f"status:{job_id}")
        if status is None:
            return jsonify({"error": "job_id no encontrado"}), 404
        return jsonify({"job_id": job_id, "status": "processing"}), 202
    return jsonify({"job_id": job_id, "status": "completed", "image_data": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
