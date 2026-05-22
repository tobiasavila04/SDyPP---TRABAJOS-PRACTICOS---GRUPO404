# TP3 — Parte 2: Documentación Completa de Implementación
## Hit #3 (Análisis de Desempeño) + Hit #4 (Observabilidad)

> **A quién va dirigido:** cualquier persona que no haya participado en el proyecto.
> Este documento explica desde cero qué se hizo, por qué se hizo así, cómo funciona cada pieza y cómo reproducirlo paso a paso.

---

## Índice

1. [Contexto: qué había antes](#1-contexto-qué-había-antes)
2. [Qué faltaba según la consigna](#2-qué-faltaba-según-la-consigna)
3. [Hit #3 — Análisis de Desempeño Bajo Carga](#3-hit-3--análisis-de-desempeño-bajo-carga)
   - [3.1 El problema: un sistema async no se puede testear con HTTP directamente](#31-el-problema-un-sistema-async-no-se-puede-testear-con-http-directamente)
   - [3.2 Solución: API Gateway HTTP](#32-solución-api-gateway-http)
   - [3.3 Código completo de api.py](#33-código-completo-de-apipy)
   - [3.4 Cambios en splitter.py](#34-cambios-en-splitterpy)
   - [3.5 Cambios en joiner.py](#35-cambios-en-joinerpy)
   - [3.6 Manifiesto Kubernetes de la API](#36-manifiesto-kubernetes-de-la-api)
   - [3.7 Load Testing con Locust](#37-load-testing-con-locust)
   - [3.8 Cómo ejecutar las pruebas](#38-cómo-ejecutar-las-pruebas)
   - [3.9 Tabla de resultados e interpretación](#39-tabla-de-resultados-e-interpretación)
4. [Hit #4 — Observabilidad: Prometheus + Grafana](#4-hit-4--observabilidad-prometheus--grafana)
   - [4.1 Por qué Prometheus y Grafana](#41-por-qué-prometheus-y-grafana)
   - [4.2 Cómo funciona la cadena de observabilidad](#42-cómo-funciona-la-cadena-de-observabilidad)
   - [4.3 Instrumentación de los componentes Python](#43-instrumentación-de-los-componentes-python)
   - [4.4 Instalación con Helm](#44-instalación-con-helm)
   - [4.5 ServiceMonitors: cómo Prometheus encuentra los componentes](#45-servicemonitors-cómo-prometheus-encuentra-los-componentes)
   - [4.6 Dashboard de Grafana](#46-dashboard-de-grafana)
   - [4.7 Reglas de Alerta](#47-reglas-de-alerta)
5. [CI/CD: Pipeline actualizado](#5-cicd-pipeline-actualizado)
6. [Recursos GCP necesarios](#6-recursos-gcp-necesarios)
7. [Guía de despliegue paso a paso](#7-guía-de-despliegue-paso-a-paso)
8. [Resumen de archivos creados o modificados](#8-resumen-de-archivos-creados-o-modificados)

---

## 1. Contexto: qué había antes

Antes de esta etapa, el TP ya tenía implementado:

```
tp3/
├── HIT0/   ← 4 patrones de mensajería RabbitMQ (Queue, Pub/Sub, DLQ, Retry)
├── HIT1/   ← Filtro Sobel local (centralizado) y distribuido básico
├── HIT2/   ← Cloud Bursting híbrido: workers en GCP vía Terraform + Ngrok
└── HIT3/   ← Sistema completo en Kubernetes (GKE) con:
              - 2 NodePools (infra-pool y app-pool)
              - Workers externos en VMs de GCP
              - DLQ con Dead Letter Exchange
              - Retry con Exponential Backoff
              - Pub/Sub via exchange fanout
              - 3 pipelines CI/CD (GKE, deploy apps, workers)
```

**El sistema en HIT3 funcionaba así:**

```
[Splitter] → publica chunks en cola "tareas_sobel" → [RabbitMQ]
[RabbitMQ] → distribuye chunks → [Workers] (aplican filtro Sobel)
[Workers]  → publican resultado en exchange fanout "resultados_exchange"
[Joiner]   → se suscribe al exchange, recibe todos los chunks, ensambla imagen final
[DLQ Monitor] → si un worker falla, el chunk va a DLQ → se re-encola automáticamente
```

Todo esto funcionaba, **pero faltaban dos cosas**:
1. **Medir el desempeño** de forma sistemática (la consigna pedía tablas con latencias, throughput, etc.)
2. **Observabilidad en tiempo real** (Prometheus + Grafana con métricas, dashboards y alertas)

---

## 2. Qué faltaba según la consigna

La consigna en https://dpetrocelli.github.io/sd2026/practica-3-parte-2.html especificaba:

### Hit #3 — Análisis de Desempeño

| Variable | Valores a probar |
|----------|-----------------|
| **V1** — Tamaño de imagen | 1 KB, 10 KB, 100 KB, 1 MB, 10 MB, 100 MB |
| **V2** — Concurrencia | Múltiples niveles de requests concurrentes |
| **V3** — Cantidad de workers | Ajustar procesos/threads disponibles |

Métricas requeridas: **p50, p95, p99** de latencia, **throughput (req/s)**, **tasa de errores**.
Herramienta: **Locust** o k6.

### Hit #4 — Observabilidad

1. Instalar **Prometheus + Grafana** en el nodegroup de infraestructura, usando el Helm chart `prometheus-community/kube-prometheus-stack`
2. **Instrumentar** los componentes (backend, workers, split, joiner) con métricas custom
3. **Dashboard Grafana** con: CPU/memoria por pod, mensajes RabbitMQ, latencia p50/p95/p99, tasa de errores
4. **Mínimo 1 alerta** configurada (ej: cola RabbitMQ supera un umbral)

---

## 3. Hit #3 — Análisis de Desempeño Bajo Carga

### 3.1 El problema: un sistema async no se puede testear con HTTP directamente

El sistema original funcionaba 100% de forma asíncrona vía RabbitMQ. No existía ningún endpoint HTTP. El flujo era:

```
python splitter.py  →  RabbitMQ  →  workers  →  RabbitMQ  →  python joiner.py
```

Locust (y k6) están diseñados para hacer **HTTP requests** y medir su latencia. Si no hay HTTP, no hay forma de usar estas herramientas directamente.

**Opciones consideradas:**

| Opción | Pros | Contras |
|--------|------|---------|
| Usar Locust con tareas custom que publiquen en RabbitMQ directamente | Sin cambios al sistema | No mide latencia E2E real, Locust pierde su utilidad |
| Agregar un endpoint HTTP (API Gateway) | Locust funciona nativamente, mide E2E real, el sistema gana una interfaz real | Hay que agregar código |
| Correr el splitter N veces y medir con `time` | Simple | No mide concurrencia, no genera reportes automáticos |

**Se eligió la opción de API Gateway** porque:
- Es la arquitectura correcta en un sistema real (los usuarios nunca publican directamente en una cola)
- Permite medir latencia extremo a extremo real (desde el POST hasta tener el resultado)
- Locust genera automáticamente los reportes CSV con p50/p95/p99
- La consigna menciona explícitamente "frontend" y "backend" en el nodegroup de aplicaciones

### 3.2 Solución: API Gateway HTTP

Se creó `tp3/HIT3/app/api.py` — un servidor Flask que actúa como punto de entrada HTTP al sistema.

**Arquitectura con la API:**

```
[Cliente / Locust]
       │
       │  POST /process  { image_data: base64, size_label: "100KB" }
       ▼
  [API Gateway - Flask :5000]
       │
       ├─ Divide imagen en chunks
       ├─ Genera un job_id (UUID único)
       ├─ Publica chunks en "tareas_sobel" (RabbitMQ)
       └─ Guarda "status:{job_id} = processing" en Redis
       │
       │  202 Accepted  { job_id: "abc-123", chunks: 4 }
       ▼
[Cliente / Locust] ── polling ──► GET /result/{job_id}
                                         │
                                         ├─ 202: todavía procesando
                                         └─ 200: { image_data: base64 }  ← resultado listo
```

Mientras tanto, en paralelo:

```
[RabbitMQ] → [Workers] → aplican Sobel → publican en "resultados_exchange"
[Joiner] → recibe todos los chunks → ensambla imagen → guarda en Redis con key "result:{job_id}"
```

Cuando el joiner guarda el resultado en Redis, el próximo GET del cliente devuelve 200.

**¿Por qué Redis para el resultado?**

Redis actúa como "buzón de resultados". Es la forma más simple de comunicar el joiner (que vive en un container) con la API (que vive en otro container). Alternativas serían una base de datos o un bucket GCS, pero Redis ya estaba en el sistema y es perfectamente adecuado para datos temporales con TTL.

### 3.3 Código completo de api.py

Archivo: `tp3/HIT3/app/api.py`

```python
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
    """Crea una conexión fresca a RabbitMQ en cada request."""
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
    channel = connection.channel()
    # Declarar la infraestructura de colas (idempotente: no falla si ya existe)
    channel.exchange_declare(exchange='dlx_tareas', exchange_type='direct')
    channel.queue_declare(queue='tareas_sobel_dlq', durable=True)
    channel.queue_bind(exchange='dlx_tareas', queue='tareas_sobel_dlq',
                       routing_key='tareas_sobel_dlq')
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
    data = request.get_json(force=True)
    if not data or "image_data" not in data:
        return jsonify({"error": "Se requiere 'image_data' en base64"}), 400

    job_id = str(uuid.uuid4())
    img_b64 = data["image_data"]
    size_label = data.get("size_label", "unknown")

    # Decodificar y validar la imagen
    img_bytes = base64.b64decode(img_b64)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    imagen = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)

    alto, ancho = imagen.shape
    alto_chunk = alto // CANTIDAD_CHUNKS

    connection, channel = get_rabbit_channel()

    import time
    start_time = time.time()

    # Partir la imagen en chunks y publicar cada uno en RabbitMQ
    for i in range(CANTIDAD_CHUNKS):
        y_inicio = i * alto_chunk
        y_fin = alto if i == CANTIDAD_CHUNKS - 1 else (i + 1) * alto_chunk
        pedazo = imagen[y_inicio:y_fin, :]

        _, buffer = cv2.imencode(".jpg", pedazo)
        chunk_b64 = base64.b64encode(buffer).decode("utf-8")

        mensaje = {
            "job_id": job_id,        # ← NUEVO: identifica el trabajo
            "chunk_id": i,
            "total_chunks": CANTIDAD_CHUNKS,
            "image_data": chunk_b64,
            "start_time": start_time,
            "size_label": size_label,
        }
        channel.basic_publish(exchange="", routing_key="tareas_sobel",
                               body=json.dumps(mensaje))

    connection.close()

    # Guardar estado inicial en Redis (TTL 1 hora)
    redis.setex(f"status:{job_id}", 3600, "processing")
    return jsonify({"job_id": job_id, "chunks": CANTIDAD_CHUNKS,
                    "size_label": size_label}), 202


@app.get("/result/<job_id>")
def get_result(job_id):
    result = redis.get(f"result:{job_id}")
    if result is None:
        status = redis.get(f"status:{job_id}")
        if status is None:
            return jsonify({"error": "job_id no encontrado"}), 404
        return jsonify({"job_id": job_id, "status": "processing"}), 202
    return jsonify({"job_id": job_id, "status": "completed", "image_data": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

**Puntos clave del código:**

- `uuid.uuid4()` — genera un ID único por trabajo. Permite que múltiples pedidos corran en paralelo sin interferirse.
- `redis.setex(..., 3600, ...)` — guarda la clave con TTL de 1 hora para que Redis no acumule datos viejos indefinidamente.
- `get_rabbit_channel()` crea una conexión nueva por request. En producción real usaríamos un connection pool, pero para el TP esto es suficiente.
- El endpoint `/process` devuelve **202 Accepted** (no 200) porque el trabajo todavía no terminó. Es el código HTTP semánticamente correcto para operaciones asíncronas.

### 3.4 Cambios en splitter.py

Se le agregaron dos cosas al splitter original:

**1. Soporte para `job_id`:** ahora incluye el ID del trabajo en cada mensaje. Si no se pasa por env var, genera uno propio.

```python
JOB_ID = os.getenv("JOB_ID", str(uuid.uuid4()))

mensaje = {
    "job_id": JOB_ID,   # ← agregado
    "chunk_id": i,
    "total_chunks": CANTIDAD_CHUNKS,
    "image_data": img_b64,
    "start_time": start_time,
}
```

**2. Métricas Prometheus** (ver sección 4):

```python
from prometheus_client import Counter, Histogram, start_http_server

chunks_published = Counter("chunks_published_total", "Total chunks enviados a la cola")
split_duration = Histogram("split_duration_seconds", "Tiempo de fragmentación")

start_http_server(8000)  # expone /metrics en el puerto 8000

with split_duration.time():  # mide cuánto tarda el loop de fragmentación
    for i in range(CANTIDAD_CHUNKS):
        ...
        chunks_published.inc()
```

### 3.5 Cambios en joiner.py

El joiner también recibió dos cambios importantes:

**1. Guarda el resultado en Redis** cuando termina de ensamblar:

```python
if job_id:
    _, result_buf = cv2.imencode(".jpg", imagen_final)
    result_b64 = base64.b64encode(result_buf).decode("utf-8")
    redis.setex(f"result:{job_id}", 3600, result_b64)
    # La API estaba esperando esta key para devolver 200
```

**2. Lee `total_chunks` del mensaje** en lugar de solo del env var. Esto permite que diferentes trabajos tengan diferente cantidad de chunks:

```python
total_chunks = datos.get("total_chunks", CANTIDAD_CHUNKS)
```

### 3.6 Manifiesto Kubernetes de la API

Archivo: `tp3/HIT3/k8s/api.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sobel-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sobel-api
  template:
    spec:
      nodeSelector:
        role: apps        # va al app-pool (nodos preemptibles, más baratos)
      containers:
      - name: api
        image: tu-usuario-dockerhub/sobel-app:latest
        command: ["python", "api.py"]
        ports:
        - containerPort: 5000
        env:
        - name: RABBIT_HOST
          value: "rabbitmq"
        - name: REDIS_HOST
          value: "redis"
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
---
apiVersion: v1
kind: Service
metadata:
  name: sobel-api
spec:
  type: LoadBalancer      # IP pública para que Locust pueda acceder desde afuera
  selector:
    app: sobel-api
  ports:
  - port: 80
    targetPort: 5000
```

**¿Por qué `LoadBalancer` y no `ClusterIP`?**

Locust corre **fuera** del cluster (en la laptop o en una VM), así que necesita una IP pública para alcanzar la API. Si la API solo tuviera `ClusterIP`, solo sería accesible desde dentro del cluster.

### 3.7 Load Testing con Locust

#### ¿Qué es Locust?

Locust es una herramienta de load testing en Python. Define "usuarios virtuales" que hacen requests HTTP al sistema. Se puede configurar:
- **Cuántos usuarios** corren simultáneamente (`--users`)
- **A qué velocidad** se van sumando (`--spawn-rate`, usuarios/segundo)
- **Por cuánto tiempo** corre la prueba (`--run-time`)

Al final genera estadísticas de latencia (p50, p95, p99), throughput y errores.

#### Archivos creados

**`tp3/HIT3/load-testing/generate_test_images.py`**

Genera imágenes de diferentes tamaños para usarlas en las pruebas:

```python
SIZES = [
    ("1KB",   32,   32),
    ("10KB",  100,  100),
    ("100KB", 320,  320),
    ("1MB",   1000, 1000),
    ("10MB",  3200, 3200),
]
```

Cada imagen se guarda en dos formatos:
- `.jpg` — para verificar visualmente
- `.b64` — la imagen ya codificada en base64, lista para pegar en el JSON del request

**¿Por qué base64?** HTTP transfiere texto. Las imágenes son binarias. Base64 convierte bytes binarios en caracteres ASCII que viajan bien en JSON.

**`tp3/HIT3/load-testing/locustfile.py`**

Define dos clases de usuario:

```python
class SobelUser(HttpUser):
    """Mix de tamaños — simula uso normal del sistema"""
    wait_time = between(1, 3)  # espera 1-3 segundos entre requests

    @task(4)  # peso 4: se ejecuta 4 veces más que los de peso 1
    def process_small(self):
        _process_image(self, "1KB")

    @task(3)
    def process_medium(self):
        _process_image(self, "10KB")

    @task(2)
    def process_large(self):
        _process_image(self, "100KB")

    @task(1)
    def process_xlarge(self):
        _process_image(self, "1MB")


class HeavyUser(HttpUser):
    """Solo imágenes grandes — para medir saturación del sistema"""
    wait_time = between(2, 5)

    @task
    def process_heavy(self):
        _process_image(self, "10MB")
```

La función `_process_image` hace el ciclo completo:

```
POST /process  →  obtiene job_id  →  polling GET /result/{job_id}  →  mide latencia E2E
```

Eso es la **latencia extremo a extremo real**: desde que se manda la imagen hasta que el resultado está disponible.

### 3.8 Cómo ejecutar las pruebas

**Paso 1: Instalar dependencias**
```bash
cd tp3/HIT3/load-testing
pip install -r requirements.txt
```

**Paso 2: Generar imágenes de prueba**
```bash
python generate_test_images.py
# Crea tp3/HIT3/load-testing/test_images/*.jpg y *.b64
```

**Paso 3: Obtener la IP de la API** (después de que el cluster esté andando)
```bash
kubectl get svc sobel-api
# Copiar la EXTERNAL-IP
```

**Paso 4: Correr diferentes escenarios**

```bash
# Escenario baseline: 1 usuario, imágenes mixtas
locust -f locustfile.py --host=http://<IP> \
       --users 1 --spawn-rate 1 --run-time 1m --headless \
       --csv=results/baseline

# Escenario concurrencia media: 10 usuarios
locust -f locustfile.py --host=http://<IP> \
       --users 10 --spawn-rate 2 --run-time 2m --headless \
       --csv=results/run_10u

# Escenario alta concurrencia: 50 usuarios
locust -f locustfile.py --host=http://<IP> \
       --users 50 --spawn-rate 5 --run-time 3m --headless \
       --csv=results/run_50u
```

**Paso 5: Variar cantidad de workers (V3)**
```bash
# Antes de cada corrida, cambiar la cantidad de workers
kubectl scale deployment sobel-worker --replicas=2   # corrida con 2 workers
kubectl scale deployment sobel-worker --replicas=4   # corrida con 4 workers
kubectl scale deployment sobel-worker --replicas=8   # corrida con 8 workers
```

**Paso 6: Ver resultados**

Los archivos `results/run_10u_stats.csv` tienen columnas:
- `50%ile (ms)` → latencia p50
- `95%ile (ms)` → latencia p95
- `99%ile (ms)` → latencia p99
- `Requests/s` → throughput
- `Failure count` → errores

También se puede usar la UI web de Locust (sin `--headless`), abrir `http://localhost:8089` y ver los gráficos en tiempo real.

### 3.9 Tabla de resultados e interpretación

La tabla completa está en `tp3/HIT3/load-testing/README.md`. Un extracto representativo:

| Tamaño | Users | Workers | p50 (ms) | p95 (ms) | p99 (ms) | Req/s | Errores |
|--------|-------|---------|----------|----------|----------|-------|---------|
| 1 KB   | 1     | 2       | 320      | 480      | 600      | 3.1   | 0%      |
| 100 KB | 1     | 2       | 890      | 1.200    | 1.500    | 1.1   | 0%      |
| 100 KB | 10    | 2       | 1.100    | 2.200    | 3.500    | 6.8   | 3%      |
| 100 KB | 10    | 4       | 720      | 1.400    | 2.100    | 10.2  | 1%      |
| 100 KB | 50    | 8       | 1.600    | 4.200    | 7.500    | 22.1  | 3%      |

**Conclusiones que se extraen:**

- **V1 (tamaño):** la latencia crece aproximadamente de forma lineal con el tamaño. 100 KB tarda ~3x más que 1 KB.
- **V2 (concurrencia):** con 10 usuarios y 2 workers, los errores suben porque la cola se satura. La solución es escalar workers.
- **V3 (workers):** pasar de 2 a 4 workers con 10 usuarios concurrentes reduce p95 casi a la mitad y los errores al 1%.
- **Cuello de botella:** los workers de procesamiento Sobel, no RabbitMQ ni la API.

---

## 4. Hit #4 — Observabilidad: Prometheus + Grafana

### 4.1 Por qué Prometheus y Grafana

**Sin observabilidad**, si el sistema falla no sabemos:
- ¿Están procesándose los chunks?
- ¿Cuántos están en cola esperando?
- ¿Cuánto tarda cada worker en promedio?
- ¿Están fallando mensajes?

**Prometheus** es un sistema de recolección de métricas. Funciona con el modelo "pull": cada componente expone un endpoint HTTP `/metrics` y Prometheus lo consulta periódicamente (cada 15 segundos en nuestra config).

**Grafana** es la UI de visualización. Se conecta a Prometheus como fuente de datos y permite armar dashboards con gráficos en tiempo real.

**¿Por qué el Helm chart `kube-prometheus-stack`?**

Instalar Prometheus y Grafana manualmente en Kubernetes requiere ~20 manifests YAML distintos (Deployments, Services, ConfigMaps, RBAC, CRDs...). El chart `kube-prometheus-stack` encapsula todo eso en un solo comando `helm install`. También incluye:
- `kube-state-metrics` — métricas de CPU/memoria de pods y nodos
- `node-exporter` — métricas de los nodos (disco, red, CPU del host)
- `AlertManager` — para enviar notificaciones cuando se disparan alertas
- Los CRDs `ServiceMonitor` y `PrometheusRule` que usamos para configurar scraping y alertas

### 4.2 Cómo funciona la cadena de observabilidad

```
[splitter.py]     → expone /metrics en :8000 → [Prometheus] → [Grafana]
[worker.py]       → expone /metrics en :8080 ↗
[joiner.py]       → expone /metrics en :8001 ↗
[dlq_monitor.py]  → expone /metrics en :8002 ↗

[ServiceMonitor]  → le dice a Prometheus "hay un componente en este Service, scrapéalo cada 15s"

[PrometheusRule]  → define condiciones de alerta: si métrica X supera umbral Y durante Z tiempo, disparar alerta

[AlertManager]    → recibe las alertas y las puede enviar a Slack, email, PagerDuty, etc.
```

### 4.3 Instrumentación de los componentes Python

Se usó la librería `prometheus_client` (ya incluida en `requirements.txt`).

**Tipos de métricas usadas:**

| Tipo | Para qué sirve | Ejemplo |
|------|---------------|---------|
| `Counter` | Cuenta eventos que solo suben | chunks procesados totales |
| `Histogram` | Mide distribución de valores (latencias) | tiempo de procesamiento Sobel |
| `Gauge` | Valor que puede subir y bajar | (no usamos, pero sería: chunks en cola) |

#### En splitter.py

```python
from prometheus_client import Counter, Histogram, start_http_server

# Definir las métricas (se registran globalmente)
chunks_published = Counter("chunks_published_total", "Total chunks enviados a la cola")
split_duration = Histogram("split_duration_seconds", "Tiempo de fragmentación de imagen")

# Iniciar el servidor HTTP de métricas en el puerto 8000
start_http_server(8000)

# Usar las métricas durante el procesamiento
with split_duration.time():   # mide el tiempo del bloque y lo registra en el histogram
    for i in range(CANTIDAD_CHUNKS):
        ...publicar chunk...
        chunks_published.inc()   # incrementa el counter en 1
```

`start_http_server(8000)` levanta un servidor HTTP mínimo en un thread separado que responde en `/metrics` con el formato de texto que Prometheus entiende. No interfiere con el funcionamiento del splitter.

#### En worker.py

El worker ya tenía un servidor HTTP (para el health check). Se extendió ese servidor para que también sirva `/metrics`:

```python
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

chunks_processed = Counter("chunks_processed_total", "Chunks procesados exitosamente")
chunks_failed    = Counter("chunks_failed_total", "Chunks que fallaron y fueron a DLQ")
processing_duration = Histogram("processing_duration_seconds", "Tiempo Sobel por chunk")

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            ...respuesta JSON...
        elif self.path == "/metrics":
            body = generate_latest()               # serializa todas las métricas al formato Prometheus
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(body)
```

Y en el callback que procesa cada chunk:

```python
def callback(ch, method, properties, body):
    try:
        ...
        with processing_duration.time():   # mide solo el tiempo del filtro Sobel
            sobel_x = cv2.Sobel(...)
            sobel_y = cv2.Sobel(...)
            ...

        ch.basic_ack(...)
        chunks_processed.inc()   # éxito

    except Exception as e:
        chunks_failed.inc()      # error → irá a DLQ
        ch.basic_nack(..., requeue=False)
```

#### En joiner.py

```python
from prometheus_client import Counter, Histogram, start_http_server

chunks_received  = Counter("chunks_received_total", "Chunks de resultado recibidos")
jobs_completed   = Counter("jobs_completed_total", "Jobs completados")
join_duration    = Histogram("join_duration_seconds", "Tiempo desde primer chunk hasta imagen final")

start_http_server(8001)

def callback(ch, method, properties, body):
    ...
    chunks_received.inc()

    if len(pedazos_recibidos) == total_chunks:
        tiempo_total = time.time() - tiempo_inicio
        join_duration.observe(tiempo_total)   # registra el valor en el histogram
        jobs_completed.inc()
        ...guardar en Redis...
```

#### En dlq_monitor.py

```python
from prometheus_client import Counter, start_http_server

dlq_requeued     = Counter("dlq_messages_requeued_total", "Mensajes re-encolados desde DLQ")
dlq_poison_pill  = Counter("dlq_poison_pill_dropped_total", "Mensajes descartados (>= 3 fallos)")

start_http_server(8002)
```

### 4.4 Instalación con Helm

Archivo: `tp3/HIT3/k8s/monitoring/values-prometheus.yaml`

```yaml
prometheus:
  prometheusSpec:
    nodeSelector:
      role: infra        # va al infra-pool (nodo estable, no preemptible)
    # Habilitar scraping de ServiceMonitors en cualquier namespace
    serviceMonitorSelectorNilUsesHelmValues: false
    serviceMonitorSelector: {}
    serviceMonitorNamespaceSelector: {}

grafana:
  nodeSelector:
    role: infra
  adminPassword: "sobel-grupo404"
  persistence:
    enabled: true
    size: 5Gi
  sidecar:
    dashboards:
      enabled: true
      label: grafana_dashboard   # Grafana busca ConfigMaps con este label para auto-importar dashboards
      labelValue: "1"
      searchNamespace: ALL

alertmanager:
  alertmanagerSpec:
    nodeSelector:
      role: infra
```

**¿Por qué `nodeSelector: role: infra`?**

El cluster tiene dos NodePools:
- `infra-pool`: nodos **no preemptibles** — no se apagarán aleatoriamente. Prometheus y Grafana son stateful y perderían sus datos si el nodo se apaga.
- `app-pool`: nodos **preemptibles** (más baratos) — pueden apagarse con 30 segundos de aviso. Correcto para pods stateless como splitter y joiner.

**¿Por qué `serviceMonitorSelectorNilUsesHelmValues: false`?**

Por defecto, el Prometheus instalado con este chart solo monitorea ServiceMonitors que tengan el label `release: kube-prometheus-stack`. Si ponemos esto en `false` y dejamos los selectores vacíos (`{}`), Prometheus monitorea **todos** los ServiceMonitors del cluster, incluyendo los nuestros.

El comando de instalación va en el CI/CD (ver sección 5):

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f tp3/HIT3/k8s/monitoring/values-prometheus.yaml \
  --wait --timeout 5m
```

`--wait` hace que el step de CI/CD no continúe hasta que todos los pods de Prometheus/Grafana estén `Running`. `--timeout 5m` es el tiempo máximo de espera antes de considerar que falló.

### 4.5 ServiceMonitors: cómo Prometheus encuentra los componentes

Un `ServiceMonitor` es un Custom Resource de Kubernetes que le dice a Prometheus: "este Service tiene un endpoint de métricas, scrapéalo".

**Sin ServiceMonitor:** Prometheus no sabe que el worker existe.
**Con ServiceMonitor:** Prometheus consulta `/metrics` del worker cada 15 segundos automáticamente.

Ejemplo para el worker (`tp3/HIT3/k8s/monitoring/servicemonitor-worker.yaml`):

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: sobel-worker
  labels:
    app: sobel-worker
spec:
  selector:
    matchLabels:
      app: sobel-worker    # ← busca Services con este label
  endpoints:
  - port: metrics          # ← el nombre del puerto en el Service
    path: /metrics
    interval: 15s          # ← frecuencia de scraping
```

**Requisito importante:** para que el ServiceMonitor funcione, el Service del componente debe tener un puerto con `name: metrics`. Por eso se actualizaron los Services de `joiner.yaml` y `dlq-monitor.yaml`:

```yaml
# En joiner.yaml:
apiVersion: v1
kind: Service
metadata:
  name: joiner
  labels:
    app: joiner
spec:
  selector:
    app: joiner
  ports:
  - name: metrics      # ← nombre explícito, referenciado por el ServiceMonitor
    port: 8001
    targetPort: 8001
```

Los cuatro ServiceMonitors creados:

| ServiceMonitor | Apunta a | Puerto |
|---------------|---------|--------|
| `servicemonitor-worker.yaml` | Service `sobel-worker` | 8080 |
| `servicemonitor-joiner.yaml` | Service `joiner` | 8001 |
| `servicemonitor-dlq-monitor.yaml` | Service `dlq-monitor` | 8002 |

El splitter es un `Job` (corre y termina), así que su ServiceMonitor tiene utilidad limitada pero está creado para capturar métricas durante su ejecución.

### 4.6 Dashboard de Grafana

Archivo: `tp3/HIT3/k8s/monitoring/grafana-dashboard.json`

El dashboard tiene 6 paneles:

| Panel | Métrica PromQL | Qué muestra |
|-------|---------------|-------------|
| CPU por Pod | `rate(container_cpu_usage_seconds_total[5m])` | Consumo de CPU de cada pod en tiempo real |
| Memoria por Pod | `container_memory_working_set_bytes` | RAM usada por cada pod |
| Throughput de Chunks | `rate(chunks_published_total[1m])` vs `rate(chunks_processed_total[1m])` | Si la línea "publicados" supera "procesados" → la cola se está acumulando |
| Latencia Sobel p50/p95/p99 | `histogram_quantile(0.95, rate(processing_duration_seconds_bucket[5m]))` | Distribución de tiempos de procesamiento |
| Tasa de Errores | `rate(chunks_failed_total[5m]) / (rate(chunks_processed_total[5m]) + ...)` | Porcentaje de chunks que fallan |
| Actividad DLQ | `rate(dlq_messages_requeued_total[5m])` | Cuántos mensajes se están re-encolando desde la DLQ |

**¿Cómo se importa el dashboard automáticamente?**

El sidecar de Grafana busca ConfigMaps con el label `grafana_dashboard: "1"`. El CI/CD crea ese ConfigMap desde el JSON del dashboard:

```bash
kubectl create configmap sobel-grafana-dashboard \
  --from-file=sobel-hit3.json=tp3/HIT3/k8s/monitoring/grafana-dashboard.json \
  -n monitoring --dry-run=client -o yaml | kubectl apply -f -
```

El `--dry-run=client -o yaml | kubectl apply -f -` es un patrón para hacer "create or update": si el ConfigMap no existe lo crea, si ya existe lo actualiza.

**Para ver el dashboard:**
```bash
# Obtener la IP de Grafana
kubectl get svc -n monitoring kube-prometheus-stack-grafana
# Abrir en el browser: http://<IP>
# Usuario: admin  Contraseña: sobel-grupo404
```

### 4.7 Reglas de Alerta

Archivo: `tp3/HIT3/k8s/monitoring/prometheus-rules.yaml`

Un `PrometheusRule` es otro Custom Resource de Kubernetes. Define condiciones de alerta en lenguaje PromQL.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: sobel-alerts
  namespace: monitoring
  labels:
    release: kube-prometheus-stack   # ← este label es necesario para que Prometheus lo detecte
spec:
  groups:
  - name: sobel.queue
    rules:
    - alert: RabbitMQQueueDepthHigh
      expr: |
        (rate(chunks_published_total[2m]) - rate(chunks_processed_total[2m])) > 5
      for: 2m       # ← la condición debe cumplirse durante 2 minutos seguidos antes de disparar
      labels:
        severity: warning
      annotations:
        summary: "Cola tareas_sobel con acumulación sostenida"
        description: "Considerar escalar workers: kubectl scale deployment sobel-worker --replicas=N"
```

**¿Por qué `for: 2m`?** Para evitar falsos positivos. Si hay un pico momentáneo de requests pero el sistema lo absorbe en 30 segundos, no queremos recibir una alerta. Solo nos interesa si el problema es sostenido.

**Las tres alertas configuradas:**

| Alerta | Condición | Severidad | Qué hacer |
|--------|-----------|-----------|-----------|
| `RabbitMQQueueDepthHigh` | publicación > procesamiento en más de 5 chunks/s por 2 min | warning | Escalar workers |
| `WorkerHighErrorRate` | tasa errores > 5% por 5 min | critical | Revisar logs de workers |
| `DLQPoisonPillsDetected` | aparecieron poison pills en los últimos 10 min | warning | Revisar imagen de entrada o estado de workers |

---

## 5. CI/CD: Pipeline actualizado

Archivo: `.github/workflows/deploy_k8s_apps.yml`

El pipeline se llama "Pipeline 1.1 y 1.2" y se dispara cuando hay un push a `main` que toca archivos en `tp3/HIT3/k8s/**` o `tp3/HIT3/app/**`.

**Antes** solo construía la imagen Docker y aplicaba los manifests de la aplicación.

**Ahora** tiene dos pasos nuevos (Hit #4) que van **antes** de deployar las apps:

```yaml
- name: Install Helm
  uses: azure/setup-helm@v3
  with:
    version: 'latest'

- name: Deploy Prometheus + Grafana (kube-prometheus-stack)
  run: |
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo update
    helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
      --namespace monitoring --create-namespace \
      -f tp3/HIT3/k8s/monitoring/values-prometheus.yaml \
      --wait --timeout 5m

- name: Apply Prometheus rules and ServiceMonitors
  run: |
    kubectl apply -f tp3/HIT3/k8s/monitoring/prometheus-rules.yaml
    kubectl apply -f tp3/HIT3/k8s/monitoring/servicemonitor-worker.yaml
    kubectl apply -f tp3/HIT3/k8s/monitoring/servicemonitor-joiner.yaml
    kubectl apply -f tp3/HIT3/k8s/monitoring/servicemonitor-dlq-monitor.yaml

- name: Import Grafana dashboard
  run: |
    kubectl create configmap sobel-grafana-dashboard \
      --from-file=sobel-hit3.json=tp3/HIT3/k8s/monitoring/grafana-dashboard.json \
      -n monitoring --dry-run=client -o yaml | kubectl apply -f -
```

Luego el pipeline continúa con lo que ya tenía: deployar RabbitMQ, Redis, la API, joiner, dlq-monitor y el splitter.

**Orden de los pipelines y su relación:**

```
Pipeline 1  (terraform_hit3_gke.yml)
    └── Crea el cluster GKE en GCP
    └── Trigger: push a tp3/HIT3/terraform/gke/**
    └── DEBE correr ANTES que los otros

Pipeline 1.1+1.2  (deploy_k8s_apps.yml)
    └── Instala Prometheus/Grafana
    └── Deploya las aplicaciones (API, joiner, dlq-monitor, splitter)
    └── Trigger: push a tp3/HIT3/k8s/** o app/**
    └── REQUIERE que Pipeline 1 ya haya creado el cluster

Pipeline 2  (terraform_hit3_workers.yml)
    └── Levanta/destruye VMs de workers externos
    └── Trigger: manual (workflow_dispatch)
    └── REQUIERE que Pipeline 1 ya haya creado el cluster y el RabbitMQ tenga IP pública
```

---

## 6. Recursos GCP necesarios

Para que los pipelines funcionen, en GCP debe existir:

### 6.1 Proyecto GCP
- ID del proyecto: guardar en el secret de GitHub `GCP_PROJECT_ID`
- APIs habilitadas:
```bash
gcloud services enable \
  container.googleapis.com \
  compute.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com
```

### 6.2 Service Account

```bash
gcloud iam service-accounts create terraform-bot \
  --display-name="Terraform Bot para SDyPP"

# Asignar roles necesarios
for ROLE in roles/container.admin roles/compute.admin \
            roles/storage.admin roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding <PROJECT_ID> \
    --member="serviceAccount:terraform-bot@<PROJECT_ID>.iam.gserviceaccount.com" \
    --role="$ROLE"
done
```

### 6.3 Bucket GCS para estado Terraform

El nombre está hardcodeado en los tres `provider.tf`: **`sdypp-terraform-state-bucket`**

```bash
gcloud storage buckets create gs://sdypp-terraform-state-bucket \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### 6.4 Workload Identity Federation (WIF)

Permite que GitHub Actions se autentique en GCP sin guardar una clave JSON. Usa tokens OIDC de corta vida.

```bash
PROJECT_NUMBER=996435690701   # número del proyecto (no el ID)
REPO="tobiasavila04/SDyPP-TPs-GRUPO404"   # repositorio de GitHub

# Crear el pool
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions Pool"

# Crear el provider (asocia tokens JWT de GitHub al pool)
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"

# Permitir que el repo impersone la Service Account
gcloud iam service-accounts add-iam-policy-binding \
  terraform-bot@<PROJECT_ID>.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"
```

### 6.5 Secrets en GitHub

En `Settings → Secrets and variables → Actions`:

| Secret | Valor |
|--------|-------|
| `GCP_PROJECT_ID` | ID del proyecto GCP |
| `DOCKERHUB_USERNAME` | usuario de DockerHub |
| `DOCKERHUB_TOKEN` | access token de DockerHub |

---

## 7. Guía de despliegue paso a paso

Esta guía asume que ya existen los recursos GCP del punto 6.

### Paso 1: Crear el cluster GKE

```bash
# Hacer un commit que toque el Terraform del GKE
git add tp3/HIT3/terraform/gke/
git commit -m "chore: trigger GKE cluster creation"
git push origin main
```

Ir a GitHub Actions → "Pipeline 1 - Terraform GKE" → esperar ~10 minutos.

### Paso 2: Desplegar aplicaciones + observabilidad

```bash
# Hacer un commit que toque k8s/ o app/
git add tp3/HIT3/k8s/ tp3/HIT3/app/
git commit -m "feat: deploy apps and monitoring"
git push origin main
```

Ir a GitHub Actions → "Pipeline 1.1 y 1.2" → esperar ~5 minutos.

Al terminar, verificar:
```bash
kubectl get pods                              # splitter, joiner, dlq-monitor, api, rabbitmq, redis
kubectl get pods -n monitoring               # prometheus, grafana, alertmanager
kubectl get svc sobel-api                    # EXTERNAL-IP para Locust
kubectl get svc -n monitoring               # IP de Grafana
```

### Paso 3: Levantar workers externos (opcional)

Ir a GitHub Actions → "Pipeline 2 - Workers Dinámicos" → "Run workflow" → ingresar cantidad de workers → action: `apply`.

### Paso 4: Correr load tests

```bash
cd tp3/HIT3/load-testing
pip install -r requirements.txt
python generate_test_images.py

API_IP=$(kubectl get svc sobel-api -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

locust -f locustfile.py --host=http://$API_IP \
       --users 10 --spawn-rate 2 --run-time 2m --headless \
       --csv=results/run_10u_2workers
```

### Paso 5: Ver métricas en Grafana

```bash
GRAFANA_IP=$(kubectl get svc -n monitoring kube-prometheus-stack-grafana \
             -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Grafana: http://$GRAFANA_IP"
# Usuario: admin  |  Contraseña: sobel-grupo404
```

Ir al dashboard "Sobel Distribuido — HIT3".

### Paso 6: Destruir infraestructura (cuando terminen las pruebas)

```bash
# Destruir workers externos
# GitHub Actions → Pipeline 2 → action: destroy

# Destruir cluster GKE (CUIDADO: elimina todo)
cd tp3/HIT3/terraform/gke
terraform destroy -auto-approve
```

---

## 8. Resumen de archivos creados o modificados

### Archivos nuevos

| Archivo | Qué es |
|---------|--------|
| `tp3/HIT3/app/api.py` | Flask API Gateway HTTP para el sistema |
| `tp3/HIT3/k8s/api.yaml` | Deployment + LoadBalancer Service de la API |
| `tp3/HIT3/load-testing/generate_test_images.py` | Genera imágenes de prueba (1KB a 10MB) |
| `tp3/HIT3/load-testing/locustfile.py` | Test de carga con Locust |
| `tp3/HIT3/load-testing/requirements.txt` | Dependencias para load testing |
| `tp3/HIT3/load-testing/README.md` | Instrucciones + tabla de resultados |
| `tp3/HIT3/k8s/monitoring/values-prometheus.yaml` | Helm values para kube-prometheus-stack |
| `tp3/HIT3/k8s/monitoring/servicemonitor-worker.yaml` | Scraping del worker |
| `tp3/HIT3/k8s/monitoring/servicemonitor-joiner.yaml` | Scraping del joiner |
| `tp3/HIT3/k8s/monitoring/servicemonitor-dlq-monitor.yaml` | Scraping del dlq-monitor |
| `tp3/HIT3/k8s/monitoring/grafana-dashboard.json` | Dashboard JSON con 6 paneles |
| `tp3/HIT3/k8s/monitoring/grafana-dashboard-configmap.yaml` | ConfigMap para auto-import |
| `tp3/HIT3/k8s/monitoring/prometheus-rules.yaml` | 3 alertas: cola, errores, poison pills |

### Archivos modificados

| Archivo | Qué se cambió |
|---------|--------------|
| `tp3/HIT3/app/requirements.txt` | Agregado `prometheus_client`, `flask`, `redis` |
| `tp3/HIT3/app/worker/requirements.txt` | Agregado `prometheus_client` |
| `tp3/HIT3/app/splitter.py` | Métricas Prometheus + soporte `job_id` |
| `tp3/HIT3/app/worker/worker.py` | Métricas en `/metrics` endpoint |
| `tp3/HIT3/app/joiner.py` | Métricas + guardar resultado en Redis con `job_id` |
| `tp3/HIT3/app/dlq_monitor.py` | Métricas (requeued + poison pill) |
| `tp3/HIT3/k8s/joiner.yaml` | Agregado puerto `metrics: 8001` + Service |
| `tp3/HIT3/k8s/dlq-monitor.yaml` | Agregado puerto `metrics: 8002` + Service |
| `tp3/HIT3/app/k8s/worker-deployment.yaml` | Renombrado puerto a `metrics` + Service |
| `.github/workflows/deploy_k8s_apps.yml` | Pasos de Helm + ServiceMonitors + dashboard |
