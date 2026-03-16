# HIT #2 - Reconexión automática del cliente A

## Descripción

Extensión del HIT #1: el nodo A ahora implementa **reconexión automática**. Si B cierra la
conexión o es terminado abruptamente, A detecta el error y reintenta conectarse cada
`RECONNECT_DELAY` segundos hasta restablecer la comunicación.

El nodo B se mantiene igual en esencia, pero ahora acepta múltiples conexiones en un loop para
poder recibir los reintentos de A.

## Diagrama de Arquitectura

```
┌─────────────────┐    intento #1   ┌─────────────────┐
│    Nodo A       │ ──── saludo ───►│    Nodo B       │
│  (client_a.py)  │ ◄─── respuesta ─│  (server_b.py)  │
│                 │                 │  [B se cae]     │
│  [espera 3s]    │                 └─────────────────┘
│                 │
│                 │    intento #2   ┌─────────────────┐
│                 │ ── ECONNREFUSED │    Nodo B       │
│  [espera 3s]    │   (B no corre)  │  [B aun caido]  │
│                 │                 └─────────────────┘
│                 │
│                 │    intento #3   ┌─────────────────┐
│                 │ ──── saludo ───►│    Nodo B       │
│                 │ ◄─── respuesta ─│  [B volvio]     │
└─────────────────┘                 └─────────────────┘
```

## Cómo ejecutar

Requiere Python 3.x (sin dependencias externas, solo stdlib).

### 1. Iniciar el servidor B

```bash
python3 tp1/HIT2/server_b.py
```

### 2. Iniciar el cliente A (en otra terminal)

```bash
python3 tp1/HIT2/client_a.py
```

A se conecta, saluda y vuelve a intentarlo cada 3 segundos.

### 3. Probar la reconexión

Con ambos corriendo, matá B con `Ctrl+C`. A detectará el error y mostrará:

```
[A] Error de conexion: [Errno 61] Connection refused
[A] Reintentando en 3 segundos...
```

Cuando volvés a levantar B, A se reconecta automáticamente en el próximo intento.

## Decisiones de Diseño

- **Loop infinito en A con `time.sleep`**: la reconexión se implementa con un delay fijo entre
  intentos (`RECONNECT_DELAY = 3s`).
- **Captura de excepciones de red**: se capturan `ConnectionRefusedError` (B no está corriendo),
  `ConnectionResetError` (B cerró abruptamente) y `OSError` (errores de red genéricos) para cubrir los distintos escenarios de fallo.
- **Nuevo socket por intento**: se crea un socket nuevo en cada iteración del loop en lugar de reusar el anterior. Un socket que falló queda en estado inválido y debe descartarse.
- **B acepta múltiples conexiones**: el servidor ahora tiene un `while True` para poder recibir los reintentos de A sin necesidad de reiniciarse.
