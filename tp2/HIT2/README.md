# HIT 2 — Pool de Workers con Relojes de Lamport

## Descripción

Evolución del HIT 1: en lugar de crear containers efímeros por cada tarea, se levanta un pool de N workers al inicio. Las tareas se encolan con prioridad basada en timestamps de Lamport y se procesan en orden por los workers disponibles.

## Arquitectura

```
Cliente (lamport_ts=5) ──POST /task──▶  Servidor (Flask :6000)
                                             │
                                             ├── RelojLamport.actualizar(5) → ts=6
                                             ├── ColaTareas.encolar(ts=6, tarea)
                                             │
                                     ┌───────┴───────┐
                                     ▼               ▼
                                Worker-1          Worker-2  ...  Worker-N
                              (container :P1)   (container :P2)
                                     │               │
                                     └── desencolar() → procesar → resultado
```

## Archivos

| Archivo | Descripción |
|---|---|
| `server.py` | Servidor con pool de workers, cola de prioridad (Lamport) y exclusión mutua. Puerto 6000. |
| `client.py` | Cliente CLI con soporte para enviar timestamps de Lamport. |
| `benchmark.py` | Herramienta de benchmarking que mide throughput (tareas/min) con distintas cantidades de workers. |
| `requirements.txt` | Dependencias Python. |

## Conceptos implementados

- **Reloj de Lamport**: Cada tarea recibe un timestamp lógico. El servidor actualiza su reloj con `max(local, recibido) + 1`.
- **Cola con exclusión mutua**: Min-heap protegido con `threading.Lock`. Las tareas se procesan en orden de timestamp.
- **Condition variables**: Los workers esperan (`wait`) cuando la cola está vacía y se despiertan (`notify`) cuando llega una tarea.
- **Pool de workers**: N containers pre-levantados al inicio, cada uno atendido por un hilo dedicado.

## Uso

### 1. Iniciar el servidor

```bash
# Con 4 workers (default)
python server.py

# Con 8 workers y delay simulado de 2 segundos
MAX_WORKERS=8 TASK_DELAY=2 python server.py
```

### 2. Enviar tareas

```bash
# Sin timestamp de Lamport
python client.py --operacion suma --valores 10 20 30

# Con timestamp de Lamport
python client.py --operacion resta --valores 100 25 --lamport 5
```

### 3. Benchmark

```bash
# 10 tareas concurrentes contra el servidor actual
python benchmark.py --tareas 10

# Benchmark completo: levanta el servidor con 1, 2, 4 y 8 workers
python benchmark.py --completo --tareas 10 --delay 2
```

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `MAX_WORKERS` | 4 | Cantidad de containers worker a levantar. |
| `TASK_DELAY` | 0 | Delay simulado (segundos) por tarea para testing. |
| `TASK_IMAGE` | `tobiasavila142/servicio-tareas:latest` | Imagen Docker de los workers. |
