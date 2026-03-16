# HIT #6 - Registro de Contactos (Nodo D)

## Descripción

Introduce un nuevo tipo de nodo: **D**, que actúa como registro de contactos.

- **Node D** expone un servidor **TCP** (puerto 9000) donde los nodos C se registran,
  y un servidor **HTTP** (puerto 8080) con endpoints de estado y listado.
- **Node C** ya no necesita saber las IPs de sus pares. Solo conoce a D. Al iniciarse,
  C elige un puerto aleatorio, se registra en D y recibe la lista de peers activos
  a los que les envía un saludo JSON.

## Diagrama de Arquitectura

```
                         ┌──────────────────────────────────────┐
                         │           Nodo D (EC2)               │
  curl /health ─────────►│  HTTP :8080  /health  /nodes         │
  curl /nodes  ─────────►│                                      │
                         │  TCP  :9000  ← registro de nodos C   │
                         └──────────┬───────────────────────────┘
                                    │ devuelve lista de peers
              ┌─────────────────────┼──────────────────────┐
              │                     │                      │
              ▼                     ▼                      ▼
     ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
     │  Nodo C #1     │   │  Nodo C #2     │   │  Nodo C #3     │
     │  puerto random │◄──│  saluda a C#1  │   │  saluda a C#1  │
     │                │──►│                │   │  saluda a C#2  │
     └────────────────┘   └────────────────┘   └────────────────┘
```

## Endpoints HTTP de Node D

| Método | Ruta      | Descripción                                      |
|--------|-----------|--------------------------------------------------|
| GET    | `/`       | Estado general del servicio                      |
| GET    | `/health` | Uptime, nodos registrados, puerto TCP            |
| GET    | `/nodes`  | Lista completa de nodos C registrados            |
| DELETE | `/nodes`  | Limpia el registro (para testing)                |

### Ejemplo `/health`

```json
{
  "status": "healthy",
  "registered_nodes": 2,
  "uptime_seconds": 142.3,
  "tcp_registry_port": 9000,
  "timestamp": "2026-03-15T12:01:23+00:00"
}
```

## Cómo ejecutar localmente

### 1. Iniciar Node D

```bash
uvicorn tp1.HIT6.node_d:app --host 0.0.0.0 --port 8080
```

### 2. Iniciar instancias de Node C (una por terminal)

```bash
# C1
python3 tp1/HIT6/node_c.py --registry-host 127.0.0.1 --registry-port 9000

# C2 (en otra terminal)
python3 tp1/HIT6/node_c.py --registry-host 127.0.0.1 --registry-port 9000

# C3 (en otra terminal)
python3 tp1/HIT6/node_c.py --registry-host 127.0.0.1 --registry-port 9000
```

Cada nuevo C recibe la lista de los anteriores y los saluda.

### 3. Verificar el estado

```bash
curl http://localhost:8080/health
curl http://localhost:8080/nodes
```

## Deploy en EC2

Node D es el servicio desplegado en producción. El pipeline de CI/CD
(`.github/workflows/ci.yml`) hace `git pull` + `pip install` y reinicia
`api-python.service` en cada push a `main`.

### Configurar el servicio en EC2 (una sola vez)

```bash
# Copiar el archivo de servicio
sudo cp /home/ubuntu/SD2026-GRUPO404/tp1/HIT6/api-python.service \
        /etc/systemd/system/api-python.service

# Habilitar y arrancar
sudo systemctl daemon-reload
sudo systemctl enable api-python.service
sudo systemctl start api-python.service
```

Después de eso, cada push a main actualiza el código y reinicia el servicio automáticamente. El endpoint
público http://3.144.148.19:8080/health pasará a mostrar el estado del nodo D. También hay que abrir el
puerto TCP 9000 en el Security Group de EC2 para que los nodos C externos puedan registrarse.

### Verificar desde internet

```bash
curl http://3.144.148.19:8080/health
curl http://3.144.148.19:8080/nodes
```

> **Nota:** El puerto TCP 9000 debe estar abierto en el Security Group de EC2
> para que los nodos C externos puedan registrarse.

## Decisiones de Diseño

- **Thread por conexión en D**: cada registro de C se maneja en su propio thread,
  evitando que un C lento bloquee a los demás.
- **Puerto aleatorio en C**: C hace `bind("0.0.0.0", 0)` y lee el puerto asignado
  por el SO, eliminando la necesidad de coordinación manual de puertos.
- **`_registry_lock`**: protege la lista compartida de accesos concurrentes entre
  threads de registro.
- **`_get_own_ip()`**: detecta la IP saliente de C conectándose (sin datos) a
  `8.8.8.8`, que es la IP que D necesita para que otros C puedan alcanzar a este C.
