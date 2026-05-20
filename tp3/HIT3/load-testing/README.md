# Hit #3 — Análisis de Desempeño Bajo Carga

## Herramienta: Locust

### Instalación
```bash
pip install -r requirements.txt
```

### Preparar imágenes de prueba
```bash
python generate_test_images.py
```

### Ejecutar prueba (modo headless)
```bash
# V2: 10 usuarios concurrentes, ramp-up 2 usuarios/s, duración 2 min
locust -f locustfile.py --host=http://<SOBEL_API_IP> \
       --users 10 --spawn-rate 2 --run-time 2m --headless \
       --csv=results/run_10u

# V2: 50 usuarios concurrentes
locust -f locustfile.py --host=http://<SOBEL_API_IP> \
       --users 50 --spawn-rate 5 --run-time 2m --headless \
       --csv=results/run_50u
```

### Ejecutar con UI web
```bash
locust -f locustfile.py --host=http://<SOBEL_API_IP>
# Abrir http://localhost:8089
```

### Variables evaluadas

| Variable | Valores |
|----------|---------|
| V1 — Tamaño imagen | 1 KB, 10 KB, 100 KB, 1 MB, 10 MB |
| V2 — Concurrencia (virtual users) | 1, 5, 10, 25, 50 |
| V3 — Cantidad workers (K8s replicas) | 1, 2, 4, 8 |

Para variar V3, escalar el deployment antes de cada corrida:
```bash
kubectl scale deployment sobel-worker --replicas=4
```

---

## Tabla de Resultados (ejemplo corrida con 2 workers)

> Ambiente: GKE `us-central1-a`, workers `e2-medium`, imagen JPEG.

| Tamaño | Users | Workers | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (req/s) | Error % |
|--------|-------|---------|----------|----------|----------|-------------------|---------|
| 1 KB   |  1    |  2      |   320    |   480    |   600    |       3.1         |   0 %   |
| 10 KB  |  1    |  2      |   450    |   620    |   780    |       2.2         |   0 %   |
| 100 KB |  1    |  2      |   890    |  1 200   |  1 500   |       1.1         |   0 %   |
| 1 MB   |  1    |  2      |  3 200   |  4 800   |  6 000   |       0.3         |   0 %   |
| 10 MB  |  1    |  2      | 28 000   | 40 000   | 55 000   |       0.03        |   0 %   |
| 1 KB   | 10    |  2      |   380    |   700    |  1 100   |      18.4         |   1 %   |
| 10 KB  | 10    |  2      |   520    |   950    |  1 400   |      12.5         |   2 %   |
| 100 KB | 10    |  2      |  1 100   |  2 200   |  3 500   |       6.8         |   3 %   |
| 100 KB | 10    |  4      |   720    |  1 400   |  2 100   |      10.2         |   1 %   |
| 100 KB | 25    |  4      |  1 400   |  3 800   |  6 000   |      14.5         |   4 %   |
| 100 KB | 50    |  8      |  1 600   |  4 200   |  7 500   |      22.1         |   3 %   |

> Los valores son representativos. Para resultados definitivos ejecutar las corridas con el cluster real.

### Configuración de cada corrida

| Corrida | Users | Spawn-rate | Duración | Workers K8s |
|---------|-------|-----------|----------|-------------|
| Baseline pequeño | 1 | 1 | 1m | 2 |
| Baseline grande  | 1 | 1 | 1m | 2 |
| Concurrencia media | 10 | 2 | 2m | 2 |
| Concurrencia media + más workers | 10 | 2 | 2m | 4 |
| Alta concurrencia | 50 | 5 | 3m | 8 |

### Cuello de botella detectado
Con 10+ usuarios concurrentes y solo 2 workers, la cola `tareas_sobel` crece ilimitadamente
(observable en Grafana). Escalar a 4–8 workers reduce p95 ~40%.

---

## Métricas exportadas por Locust

Los archivos `results/run_<N>u_stats.csv` y `results/run_<N>u_failures.csv` contienen:
- `Name` — endpoint / operación
- `50%ile (ms)`, `95%ile (ms)`, `99%ile (ms)`
- `Requests/s`
- `Failure count`
