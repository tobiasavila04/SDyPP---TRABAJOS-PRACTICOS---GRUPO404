# Monitoring — Arquitectura completa

## Qué es un ServiceMonitor

Un **ServiceMonitor** es un CRD (Custom Resource Definition) — un objeto de Kubernetes como un ConfigMap o un Secret, pero definido por el Prometheus Operator. Vive en etcd (la base de datos de K8s) y **no corre ningún proceso**.

El Prometheus Operator (ese sí es un pod) detecta cuando aparece o cambia un ServiceMonitor y actualiza la configuración interna de Prometheus automáticamente. Sin él, habría que editar `prometheus.yml` a mano cada vez que se agrega un servicio.

---

## Arquitectura completa

```
┌─────────────────────────── NAMESPACE: default ──────────────────────────────┐
│                                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐                 │
│  │   worker.py │    │  joiner.py  │    │  dlq_monitor.py  │                 │
│  │             │    │             │    │                  │                 │
│  │ prometheus_ │    │ prometheus_ │    │ prometheus_      │                 │
│  │ client      │    │ client      │    │ client           │                 │
│  │             │    │             │    │                  │                 │
│  │ Counter     │    │ Counter     │    │ Counter          │                 │
│  │ Histogram   │    │ Histogram   │    │                  │                 │
│  │             │    │             │    │                  │                 │
│  │ HTTP :8000  │    │ HTTP :8001  │    │ HTTP :8002       │                 │
│  │  /metrics   │    │  /metrics   │    │  /metrics        │                 │
│  └──────┬──────┘    └──────┬──────┘    └────────┬─────────┘                 │
│         │                  │                    │                            │
│  ┌──────▼──────┐    ┌──────▼──────┐    ┌────────▼─────────┐                 │
│  │  Service    │    │  Service    │    │  Service         │                 │
│  │ sobel-worker│    │  joiner     │    │  dlq-monitor     │                 │
│  │ port:metrics│    │ port:metrics│    │  port:metrics    │                 │
│  │   →8000     │    │   →8001     │    │    →8002         │                 │
│  └──────┬──────┘    └──────┬──────┘    └────────┬─────────┘                 │
│         │                  │                    │                            │
│  ┌──────▼──────┐    ┌──────▼──────┐    ┌────────▼─────────┐                 │
│  │ServiceMon.  │    │ServiceMon.  │    │ServiceMon.       │                 │
│  │sobel-worker │    │sobel-joiner │    │sobel-dlq-monitor │                 │
│  │selector:    │    │selector:    │    │selector:         │                 │
│  │ app=worker  │    │ app=joiner  │    │ app=dlq-monitor  │                 │
│  └──────┬──────┘    └──────┬──────┘    └────────┬─────────┘                 │
└─────────┼──────────────────┼────────────────────┼───────────────────────────┘
          │                  │                    │
          └──────────────────┼────────────────────┘
                             │ scrape cada 15s
                             ▼
┌──────────────── NAMESPACE: monitoring (nodo infra-pool) ────────────────────┐
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                     kube-prometheus-stack (Helm)                      │    │
│  │                                                                       │    │
│  │  ┌─────────────┐    ┌──────────────┐    ┌───────────────────────┐   │    │
│  │  │  Prometheus │    │AlertManager  │    │       Grafana          │   │    │
│  │  │             │◄───│              │    │                        │   │    │
│  │  │  TSDB       │    │ Dispara      │    │  Dashboard             │   │    │
│  │  │  (storage)  │    │ alertas      │    │  (sobel-hit3.json)     │   │    │
│  │  │             │    │              │    │                        │   │    │
│  │  └──────┬──────┘    └──────────────┘    └───────────┬───────────┘   │    │
│  │         │                                            │               │    │
│  │         │ lee PrometheusRules                        │ lee ConfigMap │    │
│  │         ▼                                            ▼               │    │
│  │  ┌─────────────────┐                    ┌───────────────────────┐   │    │
│  │  │ PrometheusRule  │                    │ ConfigMap             │   │    │
│  │  │ sobel-alerts    │                    │ sobel-grafana-        │   │    │
│  │  │                 │                    │ dashboard             │   │    │
│  │  │ - QueueDepth    │                    │ (label:               │   │    │
│  │  │ - ErrorRate >5% │                    │  grafana_dashboard=1) │   │    │
│  │  │ - PoisonPills   │                    └───────────────────────┘   │    │
│  │  └─────────────────┘                                                │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Los 4 pasos que recorre una métrica

### Paso 1 — El código expone métricas (`prometheus_client`)

Cada servicio usa la librería de Python. Hay dos variantes en el proyecto:

**joiner.py y dlq_monitor.py** — usan `start_http_server` (la forma simple):
```python
from prometheus_client import Counter, start_http_server
start_http_server(8001)  # levanta /metrics en el puerto automáticamente
```

**worker.py** — levanta su propio HTTP server a mano (para compartir el puerto con el healthcheck):
```python
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

def _start_health_server(port=8080):
    # ...
    elif self.path == "/metrics":
        # sirve generate_latest() manualmente
```

### Paso 2 — El Service de K8s nombra el puerto `metrics`

```yaml
# joiner.yaml
ports:
- name: metrics      # este nombre es el que usa el ServiceMonitor
  port: 8001
```

El nombre `metrics` es el contrato entre el Service y el ServiceMonitor.

### Paso 3 — El ServiceMonitor le dice a Prometheus dónde mirar

```yaml
# servicemonitor-joiner.yaml
spec:
  selector:
    matchLabels:
      app: joiner    # encuentra el Service que tiene este label
  endpoints:
  - port: metrics    # usa el puerto llamado "metrics" del Service
    path: /metrics
    interval: 15s    # Prometheus va a buscar métricas cada 15 segundos
```

### Paso 4 — Prometheus scrapea y evalúa reglas

El Prometheus instalado via Helm tiene configurado en `values-prometheus.yaml`:
```yaml
serviceMonitorSelectorNilUsesHelmValues: false
serviceMonitorSelector: {}          # acepta ServiceMonitors de CUALQUIER namespace
serviceMonitorNamespaceSelector: {} # idem
```

Sin esas líneas, Prometheus solo vería ServiceMonitors dentro de su propio namespace (`monitoring`) y nunca encontraría los del namespace `default`.

---

## El Prometheus Operator

El Operator es un pod que tiene un único trabajo: **vigilar objetos de Kubernetes y traducirlos a configuración de Prometheus**.

```
                    K8s API (etcd)
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ServiceMonitor  PrometheusRule  Alertmanager
    (nuevo/cambiado)     │            Config
         │               │               │
         └───────────────┼───────────────┘
                         │  watch (escucha eventos)
                         ▼
              ┌─────────────────────┐
              │  Prometheus Operator │
              │       (pod)          │
              │                     │
              │  "ah, cambió algo"  │
              │   voy a regenerar   │
              │   la config         │
              └──────────┬──────────┘
                         │ monta como Secret/ConfigMap
                         ▼
              ┌─────────────────────┐
              │     Prometheus       │
              │       (pod)          │
              │                     │
              │  prometheus.yml      │  ← archivo interno regenerado
              │  (actualizado)       │
              └─────────────────────┘
```

Sin el Operator, habría que editar `prometheus.yml` a mano cada vez que se agrega un servicio:

```yaml
# prometheus.yml — sin Operator, editado a mano
scrape_configs:
  - job_name: 'sobel-worker'
    static_configs:
      - targets: ['sobel-worker-svc:8000']
    metrics_path: /metrics
    scrape_interval: 15s

  - job_name: 'joiner'          # hay que agregar esto a mano
    static_configs:
      - targets: ['joiner-svc:8001']
```

Con el Operator alcanza con hacer `kubectl apply` de un ServiceMonitor.

### Los 4 pods del stack

| Pod | Rol |
|---|---|
| `prometheus-operator` | Vigila CRDs y regenera configs |
| `prometheus-0` | Scrapea y almacena métricas |
| `alertmanager-0` | Dispara alertas |
| `grafana` | Visualiza dashboards |

---

## Las alertas: PrometheusRule

Una vez que Prometheus tiene las métricas, evalúa `prometheus-rules.yaml` cada 30s:

| Alerta | Condición | Severidad |
|---|---|---|
| `RabbitMQQueueDepthHigh` | `rate(published) - rate(processed) > 5` por 2min | warning |
| `WorkerHighErrorRate` | `failed / (processed + failed) > 5%` por 5min | critical |
| `DLQPoisonPillsDetected` | `increase(poison_pill_dropped) > 0` en 10min | warning |

---

## El dashboard de Grafana: ConfigMap con label mágico

```yaml
# grafana-dashboard-configmap.yaml
metadata:
  labels:
    grafana_dashboard: "1"   # este label es el trigger
```

Grafana tiene un sidecar que escanea todos los ConfigMaps del cluster buscando `grafana_dashboard=1`. Cuando lo encuentra, importa el JSON del dashboard automáticamente. Configurado en `values-prometheus.yaml`:

```yaml
grafana:
  sidecar:
    dashboards:
      label: grafana_dashboard
      labelValue: "1"
      searchNamespace: ALL   # busca en TODOS los namespaces
```

---

## Ciclo completo de una métrica

```
código Python
  → expone /metrics en un puerto HTTP
    → Service K8s le da un nombre ("metrics") a ese puerto
      → ServiceMonitor selecciona ese Service y configura el scrape
        → Prometheus Operator lee el ServiceMonitor y actualiza su config
          → Prometheus scrapea /metrics cada 15s y guarda en TSDB
            → PrometheusRule evalúa expresiones sobre esos datos
              → AlertManager dispara alertas si se cumplen
              → Grafana consulta Prometheus y muestra dashboards
```
