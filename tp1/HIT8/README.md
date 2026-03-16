# HIT #8 - gRPC con Protocol Buffers

## Descripción

Refactorización del HIT #5 (mensajes JSON sobre TCP) reemplazando toda la
comunicación por **gRPC con Protocol Buffers**. Se definen dos servicios en
`sd2026.proto`:

- **GreetingService** — entre nodos C (reemplaza el TCP directo del HIT #5)
- **RegistryService** — entre C y D (reemplaza el servidor TCP del HIT #6)

El endpoint HTTP `/health` de D se mantiene en FastAPI para verificación pública.

## Archivos

| Archivo              | Descripción                                      |
|----------------------|--------------------------------------------------|
| `sd2026.proto`       | Definición de mensajes y servicios               |
| `generate_stubs.sh`  | Script para generar los stubs Python con `protoc`|
| `sd2026_pb2.py`      | Stubs generados — mensajes                       |
| `sd2026_pb2_grpc.py` | Stubs generados — servicios                      |
| `node_d.py`          | Nodo D: gRPC RegistryService + HTTP FastAPI      |
| `node_c.py`          | Nodo C: gRPC GreetingService + cliente           |

## Diagrama de Arquitectura

```
Nodo C #1                   Nodo D                    Nodo C #2
gRPC :puerto_aleatorio       gRPC :50051               gRPC :puerto_aleatorio
                             HTTP :8080

     │── Register(host,port) ──────────────────────►│
     │◄─ RegisterResponse(peers=[]) ────────────────│
     │                                              │
                                                    │── Register(host,port) ──►│
                                                    │◄─ RegisterResponse(peers=[C1])
                                                    │
     │◄── Greet(from_port=C2) ─────────────────────│
     │─── GreetingResponse ───────────────────────►│
```

## Servicios definidos en `sd2026.proto`

### GreetingService
```protobuf
service GreetingService {
  rpc Greet(GreetingRequest) returns (GreetingResponse);
}
```

### RegistryService
```protobuf
service RegistryService {
  rpc Register (RegisterRequest) returns (RegisterResponse);
  rpc Health   (HealthRequest)  returns (HealthResponse);
  rpc GetNodes (NodesRequest)   returns (NodesResponse);
}
```

## Cómo ejecutar

### 0. Generar stubs (una sola vez)

```bash
pip install grpcio grpcio-tools
bash tp1/HIT8/generate_stubs.sh
```

### 1. Iniciar Node D

```bash
uvicorn tp1.HIT8.node_d:app --host 0.0.0.0 --port 8080
```

Node D arranca el servidor gRPC en el puerto 50051 automáticamente.

### 2. Iniciar instancias de Node C

```bash
# C1
python3 tp1/HIT8/node_c.py --registry-host 127.0.0.1 --registry-grpc-port 50051

# C2 (en otra terminal)
python3 tp1/HIT8/node_c.py --registry-host 127.0.0.1 --registry-grpc-port 50051
```

### 3. Verificar

```bash
curl http://localhost:8080/health
curl http://localhost:8080/nodes
```

## Comparación JSON (HIT #5) vs Protobuf (HIT #8)

Medición realizada con un mensaje `GreetingRequest` típico:

| Métrica                  | JSON (HIT #5)          | Protobuf (HIT #8)      |
|--------------------------|------------------------|------------------------|
| Tamaño del mensaje       | **133 bytes**          | **68 bytes**           |
| Reducción de tamaño      | —                      | **~49% menos**         |
| Serialización            | Manual (`json.dumps`)  | Generada (`protoc`)    |
| Deserialización          | Manual (`json.loads`)  | Generada               |
| Framing TCP              | Newline `\n` manual    | HTTP/2 (gRPC nativo)   |
| Type safety              | Ninguna en runtime     | Verificada por protoc  |
| Definición del contrato  | Implícita en el código | Explícita en `.proto`  |

### Experiencia de desarrollo

**JSON/TCP (HIT #5)**:
- `send_json` / `recv_json` escritos a mano (~15 líneas)
- Sin contrato formal — un campo mal escrito falla silenciosamente
- Framing manual con `\n` → frágil ante mensajes con saltos de línea

**gRPC/Protobuf (HIT #8)**:
- Se escribe el `.proto` una vez, `protoc` genera todo el boilerplate
- El compilador detecta campos inválidos o tipos incorrectos
- HTTP/2 maneja el framing, multiplexing y keep-alive automáticamente
- Costo inicial: instalar `grpcio-tools` y correr el generador

## Decisiones de Diseño

- **Puerto 0 en el servidor gRPC de C**: `server.add_insecure_port("[::]:0")` devuelve
  el puerto asignado por el SO, igual que la técnica de socket del HIT #6.
- **`sys.path.insert` para los stubs**: los archivos `sd2026_pb2*.py` viven en
  `tp1/HIT8/`. Se agrega ese path al inicio para que los imports funcionen tanto
  corriendo desde la raíz como desde dentro del directorio.
- **FastAPI se mantiene en D**: gRPC no reemplaza al endpoint HTTP público — el
  evaluador sigue pudiendo hacer `curl /health` sin cliente gRPC.
