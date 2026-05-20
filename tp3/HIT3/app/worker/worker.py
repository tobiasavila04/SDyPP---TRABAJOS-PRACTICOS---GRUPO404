import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2
import numpy as np
import pika
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

chunks_processed = Counter("chunks_processed_total", "Chunks procesados exitosamente")
chunks_failed = Counter("chunks_failed_total", "Chunks que fallaron y fueron a DLQ")
processing_duration = Histogram("processing_duration_seconds", "Tiempo de procesamiento Sobel por chunk")


def _start_health_server(port=8080):
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = json.dumps({"service": "sobel-worker", "status": "ok"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/metrics":
                body = generate_latest()
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    threading.Thread(target=HTTPServer(("0.0.0.0", port), _Handler).serve_forever, daemon=True).start()


print(" [*] Iniciando Worker Sobel en Docker...")

RABBIT_HOST = os.getenv("RABBIT_HOST", "rabbitmq")

_start_health_server()


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

channel.queue_declare(queue="tareas_sobel", durable=True, arguments={
    'x-dead-letter-exchange': 'dlx_tareas',
    'x-dead-letter-routing-key': 'tareas_sobel_dlq'
})


def callback(ch, method, properties, body):
    try:
        datos = json.loads(body.decode())
        chunk_id = datos["chunk_id"]
        img_b64 = datos["image_data"]

        print(f" [->] Recibido chunk {chunk_id}")

        img_bytes = base64.b64decode(img_b64)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        imagen = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)

        with processing_duration.time():
            sobel_x = cv2.Sobel(imagen, cv2.CV_64F, 1, 0, ksize=3)
            sobel_y = cv2.Sobel(imagen, cv2.CV_64F, 0, 1, ksize=3)
            sobel_combinado = cv2.magnitude(sobel_x, sobel_y)
            sobel_normalizado = np.uint8(np.absolute(sobel_combinado))

        _, buffer = cv2.imencode(".jpg", sobel_normalizado)
        res_b64 = base64.b64encode(buffer).decode("utf-8")

        mensaje_resultado = {
            "job_id": datos.get("job_id"),
            "chunk_id": chunk_id,
            "total_chunks": datos.get("total_chunks"),
            "image_data": res_b64,
        }
        ch.basic_publish(exchange="resultados_exchange", routing_key="", body=json.dumps(mensaje_resultado))

        ch.basic_ack(delivery_tag=method.delivery_tag)
        chunks_processed.inc()
        print(f" [<-] Chunk {chunk_id} procesado y enviado al exchange.")

    except Exception as e:
        print(f" [X] Error procesando chunk: {e}")
        chunks_failed.inc()
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


channel.basic_consume(queue="tareas_sobel", on_message_callback=callback, auto_ack=False)

print(" [*] Worker listo y esperando chunks...")
channel.start_consuming()
