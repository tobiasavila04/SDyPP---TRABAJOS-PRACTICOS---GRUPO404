# HIT 3 — Coordinación y Tolerancia a Fallos (Algoritmo Bully)

## Descripción

Sistema distribuido con 3 nodos detrás de un load balancer (nginx). Implementa el algoritmo Bully para elección de líder: el nodo con mayor ID se convierte en coordinador. Si el líder cae, los followers detectan la caída via heartbeat y ejecutan una nueva elección automáticamente.

## Arquitectura

```
                    Cliente
                      │
                      ▼
              ┌──────────────┐
              │ Load Balancer │
              │ nginx (:8080) │
              └──────┬───────┘
                     │ round-robin
          ┌──────────┼──────────┐
          ▼          ▼          ▼
      ┌───────┐  ┌───────┐  ┌───────┐
      │ S1    │  │ S2    │  │ S3    │
      │ ID=3  │  │ ID=2  │  │ ID=1  │
      │ :7001 │  │ :7002 │  │ :7003 │
      │LÍDER ★│  │Follower│  │Follower│
      └───────┘  └───────┘  └───────┘
           ◄── heartbeat ──    ── heartbeat ──►
```

## Archivos

| Archivo | Descripción |
|---|---|
| `node.py` | Servidor/nodo Flask con algoritmo Bully, heartbeat, procesamiento de tareas y rol dinámico (LEADER/FOLLOWER). |
| `client.py` | Cliente CLI que envía tareas al load balancer. |
| `docker-compose.yml` | Orquesta los 3 nodos + nginx. |
| `nginx.conf` | Configuración de nginx como load balancer (round-robin). |
| `Dockerfile` | Imagen Docker para cada nodo. |
| `requirements.txt` | Dependencias Python. |

## Algoritmo Bully

El nodo con **mayor ID** activo es el líder. Cuando el líder cae:

1. Un follower detecta que el líder no responde (timeout en `/health`).
2. Envía `ELECTION` a todos los nodos con ID mayor.
3. Si un nodo mayor responde `OK`, ese nodo toma el control de la elección.
4. El nodo con mayor ID que esté vivo se declara `COORDINATOR` y notifica a todos.

### Ejemplo (caída de S1, ID=3):

```
S3 (ID=1) detecta que S1 no responde (timeout heartbeat)
S3 envía ELECTION a S2 (ID=2)
S2 responde OK (tiene mayor ID que S3)
S2 no tiene nodos con ID mayor vivos → se declara COORDINATOR
S2 envía COORDINATOR a todos los nodos
S2 es el nuevo líder
```

## Roles

### Líder (COORDINATOR)
- Recibe tareas del load balancer o reenviadas por followers.
- Asigna tareas a nodos workers disponibles (round-robin).
- Mantiene registro de nodos vivos.

### Follower
- Reenvía tareas al líder.
- Ejecuta tareas asignadas por el líder via `/execute-task`.
- Monitorea al líder via heartbeat periódico.
- Inicia elección si el líder no responde.

## Uso

### 1. Levantar el cluster

```bash
docker compose up --build
```

Esto levanta:
- `node1` (ID=3, puerto 7001) — líder inicial
- `node2` (ID=2, puerto 7002) — follower
- `node3` (ID=1, puerto 7003) — follower
- `loadbalancer` (nginx, puerto 8080)

### 2. Enviar tareas

```bash
python client.py --operacion suma --valores 10 20 30
python client.py --operacion division --valores 100 5 2
```

### 3. Simular caída del líder

```bash
# Matar el líder (node1, ID=3)
docker stop node1
```

Los followers detectarán la caída en ~10-15 segundos y ejecutarán una nueva elección. El nodo con mayor ID vivo (node2, ID=2) se convertirá en el nuevo líder.

### 4. Verificar la re-elección

```bash
# Consultar estado de cada nodo
curl http://localhost:7002/status
curl http://localhost:7003/status
```

### 5. Recuperar el nodo caído

```bash
docker start node1
```

Al reiniciarse, node1 (ID=3) iniciará una elección y, al tener el mayor ID, se convertirá nuevamente en líder.

## Endpoints

| Endpoint | Método | Descripción |
|---|---|---|
| `/health` | GET | Health check + heartbeat. Retorna status, node_id, role, leader_id. |
| `/task` | POST | Recibir tarea. El líder la procesa; un follower la reenvía al líder. |
| `/execute-task` | POST | El líder asigna una tarea directamente a este nodo para ejecución. |
| `/election` | POST | Recibe mensaje ELECTION del algoritmo Bully. |
| `/coordinator` | POST | Recibe anuncio de nuevo coordinador. |
| `/status` | GET | Estado completo del nodo (rol, líder, nodos vivos, estadísticas). |

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `NODE_ID` | 1 | ID único del nodo (mayor ID = mayor prioridad). |
| `NODE_HOST` | localhost | Hostname del nodo (para comunicación entre peers). |
| `NODE_PORT` | 7001 | Puerto del servidor Flask. |
| `PEERS_JSON` | `[]` | JSON con la lista de peers: `[{"id":2,"host":"node2","port":7002}]`. |
| `HEARTBEAT_INTERVAL` | 10.0 | Intervalo (segundos) entre heartbeats al líder. |
| `HEARTBEAT_TIMEOUT` | 5.0 | Timeout (segundos) para considerar al líder caído. |
| `ELECTION_TIMEOUT` | 3.0 | Timeout (segundos) para esperar respuestas en la elección. |

## Comandos para simulación

```bash
# 1. Levantar el cluster
cd tp2/HIT3
docker-compose up --build -d

# 2. Ver estado del cluster (quién es líder, quiénes están vivos)
curl -s http://localhost:7001/status | python3 -m json.tool   # node1 (ID=3)
curl -s http://localhost:7002/status | python3 -m json.tool   # node2 (ID=2)
curl -s http://localhost:7003/status | python3 -m json.tool   # node3 (ID=1)

# 3. Enviar tareas (via Load Balancer o directo a cada nodo)
curl -s -X POST http://localhost:8080/task -H "Content-Type: application/json" \
  -d '{"operation":"suma","values":[10,20,30]}'

curl -s -X POST http://localhost:7002/task -H "Content-Type: application/json" \
  -d '{"operation":"multiplicacion","values":[5,3,2]}'

curl -s -X POST http://localhost:7003/task -H "Content-Type: application/json" \
  -d '{"operation":"division","values":[100,5,2]}'

# 4. Matar al líder (node1, ID=3)
docker stop node1

# 5. Esperar ~15 segundos y verificar nueva elección
curl -s http://localhost:7002/status | python3 -m json.tool
curl -s http://localhost:7003/status | python3 -m json.tool

# 6. Enviar tarea con nuevo líder
curl -s -X POST http://localhost:8080/task -H "Content-Type: application/json" \
  -d '{"operation":"resta","values":[100,25,15]}'

# 7. Recuperar nodo caído (vuelve a ser líder por tener mayor ID)
docker start node1

# 8. Ver logs de los nodos
docker-compose logs -f

# 9. Bajar todo
docker-compose down
```