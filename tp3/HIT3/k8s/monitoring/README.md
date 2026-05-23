# HIT 4 — Prometheus + Grafana

Si no tenés métricas, no sabés si los workers están vivos, si la cola se llenó, o si los chunks están fallando. Acá instalamos Prometheus y Grafana en el cluster y a cada servicio Python le pusimos `prometheus_client` para que exporte métricas.

## Cómo verifican los profes que funciona

### Antes que nada

Tiene que estar el cluster GKE andando (HIT3) y los pipelines de deploy tienen que haberse ejecutado al menos una vez.

### Ver qué pods hay en monitoring

```powershell
kubectl get pods -n monitoring
```

Si los pipelines anduvieron bien, deberían salir estos (o parecidos):

```
alertmanager-kube-prometheus-stack-alertmanager-0        2/2     Running
kube-prometheus-stack-grafana-xxxx                       3/3     Running
kube-prometheus-stack-operator-xxxx                      1/1     Running
kube-prometheus-stack-prometheus-0                       2/2     Running
```

Si no sale nada, el pipeline no se ejecutó. Más abajo está cómo instalarlo a mano.

### Abrir Grafana

```powershell
kubectl get svc -n monitoring kube-prometheus-stack-grafana
```

Usá la `EXTERNAL-IP` que te muestra y abrí `http://<IP>` en el navegador. Las credenciales son:

- Usuario: `admin`
- Contraseña: `sobel-grupo404`

### Encontrar el dashboard

Apenas entrás, andá a **Dashboards → Browse**. Buscá "Sobel Distribuido — HIT3". Si no está, esperá un minuto y refrescá, a veces el sidecar de Grafana tarda en importarlo.

El dashboard tiene 6 cositas:
1. **CPU por Pod** — uso de CPU de cada pod
2. **Memoria por Pod** — RAM de cada pod
3. **Throughput de Chunks** — publicados vs procesados vs recibidos
4. **Latencia Sobel** — p50/p95/p99 del filtro Sobel
5. **Tasa de Errores** — porcentaje de chunks que fallaron
6. **Actividad DLQ** — mensajes re-encolados y poison pills

Si ves los paneles vacíos, es normal, no hay actividad. Pasá al paso siguiente.

### Meterle tráfico para que se vea algo

Parate en `tp3/HIT3/load-testing/` y generá las imágenes de prueba:

```powershell
python generate_test_images.py
```

Después fijate la IP de la API:

```powershell
kubectl get svc sobel-api
```

Y mandale un par de requests con Locust, 1 solo usuario así no satura:

```powershell
locust -f locustfile.py --host=http://<API_IP> --users 1 --spawn-rate 1 --run-time 2m --headless
```

Mientras corre, volvé a Grafana y refrescá — los paneles se empiezan a llenar solos.

### Si el pipeline no instaló el monitoring, hacerlo a mano

```powershell
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack `
  --namespace monitoring --create-namespace `
  -f tp3/HIT3/k8s/monitoring/values-prometheus.yaml --wait --timeout 5m

kubectl apply -f tp3/HIT3/k8s/monitoring/servicemonitor-worker.yaml
kubectl apply -f tp3/HIT3/k8s/monitoring/servicemonitor-joiner.yaml
kubectl apply -f tp3/HIT3/k8s/monitoring/servicemonitor-dlq-monitor.yaml
kubectl apply -f tp3/HIT3/k8s/monitoring/prometheus-rules.yaml

kubectl create configmap sobel-grafana-dashboard `
  --from-file=sobel-hit3.json=tp3/HIT3/k8s/monitoring/grafana-dashboard.json `
  -n monitoring --dry-run=client -o yaml | kubectl apply -f -
```

### Las alertas

Si querés ver las reglas de alerta, en Grafana andá al menú → **Alerting → Alert rules**. Las que configuramos son tres:

1. **RabbitMQQueueDepthHigh** (warning) — salta si los chunks se publican mucho más rápido de lo que se procesan por más de 2 minutos
2. **WorkerHighErrorRate** (critical) — salta si más del 5% de los chunks fallan durante 5 minutos
3. **DLQPoisonPillsDetected** (warning) — salta si aparecen mensajes descartados por tener 3 o más fallos

O directamente desde kubectl:

```powershell
kubectl get prometheusrule -n monitoring
```

### notas

- Prometheus y Grafana están configurados para ir al nodegroup `infra-pool` (los nodos no preemptibles). Si no hay nodos en ese pool, los pods quedan en `Pending` y no andan nunca.
- Para ver las métricas crudas que exporta un servicio:
  ```powershell
  kubectl port-forward service/sobel-worker 8080:8080
  # después en otra terminal: curl http://localhost:8080/metrics
  ```
- La contraseña de Grafana está en `values-prometheus.yaml` como `sobel-grupo404`, si querés la cambiás antes de instalar.
