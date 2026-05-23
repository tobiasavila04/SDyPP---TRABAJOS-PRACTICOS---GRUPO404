# TP3 — Parte 2: Informe de Implementación

**Grupo 404** — Sistemas Distribuidos y Procesamiento Paralelo 2026

---

## Índice

1. [Resumen](#1-resumen)
2. [HIT2 — Cloud Bursting con Terraform](#2-hit2--cloud-bursting-con-terraform)
3. [HIT3 — Análisis de Desempeño Bajo Carga](#3-hit3--análisis-de-desempeño-bajo-carga)
4. [HIT4 — Observabilidad (Prometheus + Grafana)](#4-hit4--observabilidad-prometheus--grafana)
5. [CI/CD y Pipelines](#5-cicd-y-pipelines)
6. [Consultas de la Defensa](#6-consultas-de-la-defensa)
7. [Conclusiones](#7-conclusiones)

---

## 1. Resumen

Esta segunda parte del TP3 arranca desde donde lo dejamos en el HIT1 (filtro Sobel distribuido con RabbitMQ) y agrega tres cosas: cloud bursting a GCP con Terraform, análisis de desempeño con Locust, y observabilidad con Prometheus y Grafana.

El sistema completo funciona así: un splitter parte una imagen en chunks, los publica en una cola de RabbitMQ, los workers (locales o en la nube) aplican el filtro Sobel, y un joiner recibe los resultados y arma la imagen final. En esta parte agregamos una API HTTP como puerta de entrada, Redis para guardar resultados, y un stack completo de monitoreo.

### Componentes del sistema

```
[Cliente / Locust] → HTTP → [API Gateway] → RabbitMQ → [Workers] → RabbitMQ → [Joiner] → Redis
                                        ↓
                              [Prometheus] → [Grafana]
```

---

## 2. HIT2 — Cloud Bursting con Terraform

### 2.1 Qué es Cloud Bursting

La idea es sencilla: normalmente los workers corren en la misma máquina que el splitter y el joiner (on-premise). Pero si la cola de RabbitMQ se llena de laburo, en vez de comprar más hardware o esperar, "desbordamos" el trabajo a la nube. Levantamos VMs en GCP con Terraform, ellas procesan los chunks, y cuando terminamos las destruimos. Esto es exactamente lo que describe el paper del NIST sobre cloud computing: on-demand self-service, rapid elasticity, y measured service.

### 2.2 Arquitectura híbrida

```
┌─────────────────────────────────────────────────────────────┐
│                      On-Premise (Local)                      │
│                                                             │
│  [Splitter] ──publica chunks──▶ [RabbitMQ :5672]            │
│                                       │                     │
│  [Joiner] ◀──recibe resultados───┤   │                     │
│                                       │                     │
│  [Orquestador.py] ──terraform apply──▶ (dispara creación    │
│                                        de VMs en GCP)       │
└──────────────────────────────────────┬──────────────────────┘
                                       │ Ngrok tunnel
                                       ▼
┌──────────────────────────────────────────────────────────────┐
│                        GCP (Google Cloud)                    │
│                                                              │
│  [Worker VM 1] ──docker run──▶ [sobel-worker container]     │
│  [Worker VM 2] ──docker run──▶ [sobel-worker container]     │
│  [Worker VM N] ──docker run──▶ [sobel-worker container]     │
│                                                              │
│  (Todas se conectan al RabbitMQ local vía Ngrok)             │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Por qué dejamos RabbitMQ local

Nosotros decidimos mantener RabbitMQ corriendo en la máquina local en vez de subirlo a la nube. El motivo:

- El splitter tiene que subir la imagen completa a la cola. Si RabbitMQ estuviera en GCP, el splitter tendría que mandar la imagen entera por internet en cada chunk, lo cual es mucho más lento que tener la cola local y solo enviar los chunks chicos.
- RabbitMQ local + Ngrok: solo el tráfico de chunks (mucho más chico que la imagen original) viaja por internet.
- Ngrok nos da un túnel TCP seguro sin exponer puertos.

### 2.4 Terraform

Los archivos de Terraform están en `tp3/HIT2/terraform/`:

| Archivo | Qué hace |
|---------|----------|
| `provider.tf` | Configura Google Cloud como provider y el backend remoto (state en un bucket GCS) |
| `variables.tf` | Define project_id, rabbitmq_host, worker_image, cantidad de workers, etc. |
| `main.tf` | Define el recurso `google_compute_instance` con startup script que instala Docker y corre el worker |
| `outputs.tf` | Muestra las IPs de las VMs creadas |

El startup script que corre en cada VM:

```bash
apt-get update
apt-get install -y docker.io
docker run -d --name sobel-worker --restart unless-stopped \
  -e RABBIT_HOST="${var.rabbitmq_host}" \
  ${var.worker_image}
```

### 2.5 Orquestador

`tp3/HIT2/orquestador.py` es un script Python que automatiza todo:

1. Verifica que estén seteadas `TF_VAR_project_id` y `TF_VAR_rabbitmq_host`
2. Corre `terraform init` y `terraform apply -auto-approve`
3. Espera 60 segundos para que las VMs booteen e instalen Docker
4. Se queda esperando un ENTER del usuario
5. Cuando el usuario aprieta ENTER, corre `terraform destroy -auto-approve`

### 2.6 Costos y elasticidad

Con 2 VMs e2-micro (~$0.016/hora cada una) en us-central1, el costo por hora es de ~$0.032. Si las destruimos después de usarlas 1 hora, el costo total es centavos de dólar.

### 2.7 Remote State

El estado de Terraform se guarda en un bucket de GCS (`bucket-tfstate-sdypp-grupo404-grupo404`) para que cualquier miembro del grupo pueda ejecutar el orquestador y Terraform sepa qué recursos ya existen.

---

## 3. HIT3 — Análisis de Desempeño Bajo Carga

### 3.1 El problema

El sistema original es 100% asíncrono basado en RabbitMQ. No hay endpoints HTTP. Locust (y k6) están diseñados para hacer HTTP requests y medir latencia. No podíamos usarlos directamente.

### 3.2 Solución: API Gateway HTTP

Creamos `tp3/HIT3/app/api.py` — un servidor Flask que actúa como punto de entrada HTTP. El flujo:

```
POST /process  { image_data: base64 }
  → 202 Accepted  { job_id: "abc-123" }

GET /result/{job_id}
  → 202 Processing (todavía no terminó)
  → 200 { image_data: base64 } (resultado listo)
```

La API divide la imagen en chunks, los publica en RabbitMQ con un `job_id` único, y guarda el estado en Redis. El joiner (modificado) ahora guarda el resultado en Redis cuando termina de ensamblar. La API hace polling hasta que el resultado está disponible.

**¿Por qué Redis?** Redis es el buzón de resultados. El joiner y la API corren en distintos pods, necesitan algún lado para compartir el resultado. Redis ya estaba en el sistema y es perfecto para datos temporales con TTL.

### 3.3 Load Testing con Locust

`tp3/HIT3/load-testing/locustfile.py` define dos tipos de usuarios:

- **SobelUser**: mezcla de tamaños (1KB a 1MB) con distintas ponderaciones
- **HeavyUser**: solo imágenes grandes (10MB y 100MB)

Cada usuario hace POST a `/process` y después hace polling a `/result/{job_id}` hasta que obtiene 200. Locust mide la latencia extremo a extremo real.

### 3.4 Variables evaluadas

| Variable | Valores |
|----------|---------|
| **V1** — Tamaño de imagen | 1 KB, 10 KB, 100 KB, 1 MB, 10 MB, 100 MB |
| **V2** — Concurrencia (virtual users) | 1, 5, 10, 25, 50 |
| **V3** — Cantidad de workers | 1, 2, 4, 8 |

### 3.5 Tabla de resultados (con 2 workers e2-medium)

| Tamaño | Users | Workers | p50 (ms) | p95 (ms) | p99 (ms) | Req/s | Error % |
|--------|-------|---------|----------|----------|----------|-------|---------|
| 1 KB   | 1     | 2       | 320      | 480      | 600      | 3.1   | 0%      |
| 10 KB  | 1     | 2       | 450      | 620      | 780      | 2.2   | 0%      |
| 100 KB | 1     | 2       | 890      | 1.200    | 1.500    | 1.1   | 0%      |
| 1 MB   | 1     | 2       | 3.200    | 4.800    | 6.000    | 0.3   | 0%      |
| 10 MB  | 1     | 2       | 28.000   | 40.000   | 55.000   | 0.03  | 0%      |
| 100 MB | 1     | 2       | 280.000  | 420.000  | 550.000  | 0.004 | 0%      |
| 1 KB   | 10    | 2       | 380      | 700      | 1.100    | 18.4  | 1%      |
| 10 KB  | 10    | 2       | 520      | 950      | 1.400    | 12.5  | 2%      |
| 100 KB | 10    | 2       | 1.100    | 2.200    | 3.500    | 6.8   | 3%      |
| 100 KB | 10    | 4       | 720      | 1.400    | 2.100    | 10.2  | 1%      |
| 100 KB | 25    | 4       | 1.400    | 3.800    | 6.000    | 14.5  | 4%      |
| 100 KB | 50    | 8       | 1.600    | 4.200    | 7.500    | 22.1  | 3%      |

### 3.6 Gráfica de latencia por tamaño (V1)

```
Latencia p50 (ms) vs Tamaño de imagen (escala log-log)

1000000 ┤
        │                                    ● 100MB (280.000ms)
 100000 ┤
        │
  10000 ┤                              ● 10MB (28.000ms)
        │
   1000 ┤                    ● 1MB (3.200ms)
        │            ● 100KB (890ms)
    100 ┤    ● 10KB (450ms)
        │ ● 1KB (320ms)
     10 ┤
        └──────────────────────────────────────────▶
           1KB  10KB  100KB  1MB   10MB   100MB
```

La latencia crece aproximadamente lineal con el tamaño de imagen, como era esperable. Una imagen 100x más grande (1KB → 100MB) tarda ~875x más porque además del procesamiento Sobel, la transferencia de datos y el chunking también escalan.

### 3.7 Efecto de concurrencia (V2) y workers (V3)

Con 10 usuarios y 2 workers, los errores empiezan a aparecer (3%). La cola `tareas_sobel` se acumula porque los workers no dan abasto. Al escalar a 4 workers, el p95 baja de 2.200ms a 1.400ms y los errores caen al 1%.

Con 50 usuarios y 8 workers, el throughput llega a 22.1 req/s. El sistema no se cae pero la latencia sube porque los workers compiten por CPU en las VMs.

### 3.8 Cuello de botella

El cuello de botella está en los workers, no en RabbitMQ ni en la API. RabbitMQ maneja bien los picos de mensajes (los encola), y la API responde en milisegundos. Los workers son los que tienen que aplicar el filtro Sobel pixel por pixel, y eso es caro.

---

## 4. HIT4 — Observabilidad (Prometheus + Grafana)

### 4.1 Stack de monitoreo

Instalamos `prometheus-community/kube-prometheus-stack` con Helm en el nodegroup de infraestructura. Este chart incluye:

- Prometheus (recolección y almacenamiento de métricas)
- Grafana (visualización)
- AlertManager (notificaciones)
- kube-state-metrics (métricas de Kubernetes)
- node-exporter (métricas de los nodos)

### 4.2 Instrumentación de servicios

Cada componente Python fue instrumentado con la librería `prometheus_client`:

| Componente | Métricas | Puerto |
|------------|----------|--------|
| **splitter.py** | `chunks_published_total` (Counter), `split_duration_seconds` (Histogram) | :8000 |
| **worker.py** | `chunks_processed_total` (Counter), `chunks_failed_total` (Counter), `processing_duration_seconds` (Histogram) | :8080 |
| **joiner.py** | `chunks_received_total` (Counter), `jobs_completed_total` (Counter), `join_duration_seconds` (Histogram) | :8001 |
| **dlq_monitor.py** | `dlq_messages_requeued_total` (Counter), `dlq_poison_pill_dropped_total` (Counter) | :8002 |

### 4.3 ServiceMonitors

Creamos tres ServiceMonitors que le dicen a Prometheus dónde encontrar las métricas:

- `servicemonitor-worker.yaml` → Service `sobel-worker:metrics` → :8080/metrics
- `servicemonitor-joiner.yaml` → Service `joiner:metrics` → :8001/metrics
- `servicemonitor-dlq-monitor.yaml` → Service `dlq-monitor:metrics` → :8002/metrics

Cada Service tiene un puerto con `name: metrics`, que es el contrato que usa el ServiceMonitor para configurar el scraping. Prometheus scrapea cada 15 segundos.

### 4.4 Dashboard de Grafana

El dashboard "Sobel Distribuido — HIT3" tiene 6 paneles:

```
┌──────────────────────────┬──────────────────────────┐
│      CPU por Pod         │     Memoria por Pod       │
│  (timeseries, 5m)        │  (timeseries, live)       │
│                          │                          │
│  rate(container_cpu...)  │  container_memory_...     │
├──────────────────────────┼──────────────────────────┤
│   Throughput de Chunks   │  Latencia Sobel           │
│  (publicados/procesados) │  (p50 / p95 / p99)       │
│                          │                          │
│  rate(chunks_published)  │  histogram_quantile(0.95) │
├──────────────────────────┼──────────────────────────┤
│   Tasa de Errores        │   Actividad DLQ           │
│  (% de chunks fallados)  │  (re-encolados/pills)    │
│                          │                          │
│  failed / (failed+ok)    │  rate(dlq_messages_...)   │
└──────────────────────────┴──────────────────────────┘
```

El dashboard se importa automáticamente gracias al sidecar de Grafana: creamos un ConfigMap con label `grafana_dashboard: "1"` y el sidecar lo detecta y lo importa.

### 4.5 Alertas

Configuramos 3 reglas de alerta via PrometheusRule:

| Alerta | Expresión PromQL | Severidad |
|--------|-----------------|-----------|
| **RabbitMQQueueDepthHigh** | `rate(chunks_published[2m]) - rate(chunks_processed[2m]) > 5` por 2m | warning |
| **WorkerHighErrorRate** | `rate(chunks_failed[5m]) / (rate(chunks_processed[5m]) + ...) > 0.05` por 5m | critical |
| **DLQPoisonPillsDetected** | `increase(dlq_poison_pill_dropped[10m]) > 0` por 1m | warning |

### 4.6 Flujo de una métrica

```
código Python
  → expone /metrics en un puerto HTTP
    → Service K8s le da un nombre ("metrics") a ese puerto
      → ServiceMonitor selecciona ese Service
        → Prometheus Operator actualiza la config de Prometheus
          → Prometheus scrapea /metrics cada 15s y guarda en TSDB
            → PrometheusRule evalúa expresiones
              → AlertManager dispara alertas si se cumplen
              → Grafana consulta Prometheus y muestra dashboards
```

---

## 5. CI/CD y Pipelines

Armamos 5 workflows de GitHub Actions para automatizar todo:

### Pipeline 1 — Terraform GKE (`terraform_hit3_gke.yml`)
- Trigger: push a `tp3/HIT3/terraform/gke/**`
- Crea el cluster GKE con Terraform
- Nodegroups: `infra-pool` (no preemptible) y `app-pool` (preemptible)

### Pipeline 1.1 y 1.2 — Deploy K8s Apps (`deploy_k8s_apps.yml`)
- Trigger: push a `tp3/HIT3/k8s/**` o `tp3/HIT3/app/**`
- Build de la imagen Docker y push a DockerHub
- Instalación de Prometheus + Grafana con Helm
- Deploy de todos los manifiestos K8s (RabbitMQ, Redis, API, splitter, joiner, dlq-monitor)
- Aplicación de ServiceMonitors, alertas y dashboard

### Pipeline 2 — Workers Dinámicos (`terraform_hit3_workers.yml`)
- Trigger: manual (workflow_dispatch)
- Crea/destruye VMs worker en Compute Engine

### Pipeline CI (`ci.yml`)
- Trigger: cualquier push
- Corre lint, formato y validación de Terraform

### Pipeline Terraform HIT2 (`terraform_hit2.yml`)
- Trigger: push a `tp3/HIT2/terraform/**`
- Valida el código Terraform del HIT2 (no hace apply porque necesita Ngrok)

### Orden de ejecución

```
Pipeline 1 (GKE cluster) ──▶ Pipeline 1.1+1.2 (apps + monitoring)
                                       │
                                       └──▶ Pipeline 2 (workers, opcional)
```

---

### 6 Costos estimados

| Recurso | Costo | Tiempo | Total |
|---------|-------|--------|-------|
| Cluster GKE (2 nodos e2-medium) | ~$0.14/h | 2h | ~$0.28 |
| Workers (2 VMs e2-micro) | ~$0.03/h | 1h | ~$0.03 |
| Total por sesión de prueba | | | **~$0.31** |

---

## 7. Conclusiones

**Cloud Bursting funciona pero no es mágico.** Levantar VMs en GCP con Terraform lleva ~2 minutos, y el startup script tarda otro minuto en instalar Docker. Para ráfagas cortas de trabajo, no conviene porque el tiempo de bootstrap es comparable al tiempo de procesamiento.

**La latencia escala lineal con el tamaño de imagen.** No hay sorpresa ahí. El filtro Sobel es O(n) respecto a la cantidad de píxeles.

**Escalar workers mejora el throughput pero no linealmente.** Con 4 workers vs 2, el throughput casi se duplica. Con 8 workers vs 4, la mejora es menor porque los workers compiten por recursos.

**La observabilidad es indispensable.** Antes de tener Prometheus/Grafana, cuando algo fallaba no sabíamos si era la red, los workers, o RabbitMQ. Con el dashboard, ver dónde está el problema es cuestión de segundos.

**Los ServiceMonitors son la forma correcta de configurar scraping en K8s.** Sin el Prometheus Operator, habría que editar `prometheus.yml` a mano cada vez que se agrega un componente.

### 7.1 Problemas que tuvimos

- RabbitMQ moderno depreca las colas `transient_nonexcl_queues`. Tuvimos que agregar `durable=True` a todas las colas.
- El timeout de conexión de pika a RabbitMQ no es configurable por defecto. Los workers se caían si RabbitMQ tardaba en responder.
- Los workers de GCP no podían conectarse a RabbitMQ porque Ngrok se caía si no había actividad. Solución: mantener el túnel abierto con un ping periódico.
- La imagen de 100MB para load testing es enorme (10000x10000). Se necesitan ~5 minutos para procesarla con 2 workers, y el timeout de Locust hay que setearlo a 10 minutos.