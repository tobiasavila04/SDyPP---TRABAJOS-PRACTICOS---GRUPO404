# HIT #3 - Servidor B robusto ante desconexiones de A

## Descripción

Extensión del HIT #2: ahora el foco está en el **nodo B**. Si A se desconecta
abruptamente (proceso matado, crash, corte de red), B captura la excepción y
**continúa escuchando** nuevas conexiones sin necesidad de reiniciarse.

El nodo A se mantiene conectado en un loop luego del saludo, permitiendo simular
una desconexión abrupta matando su proceso.

## Diagrama de Arquitectura

```
[B escuchando]
      │
      ▼
┌─────────────────┐   conexión #1   ┌─────────────────┐
│    Nodo B       │◄────────────────│    Nodo A       │
│  (server_b.py)  │────────────────►│  (client_a.py)  │
│                 │                 │  [kill -9 A]    │
│  captura error  │                 └─────────────────┘
│  sigue en loop  │
│                 │   conexión #2   ┌─────────────────┐
│                 │◄────────────────│    Nodo A       │
│                 │────────────────►│  (nueva inst.)  │
└─────────────────┘                 └─────────────────┘
```

## Cómo ejecutar

Requiere Python 3.x (sin dependencias externas, solo stdlib).

### 1. Iniciar el servidor B

```bash
python3 tp1/HIT3/server_b.py
```

### 2. Iniciar el cliente A (en otra terminal)

```bash
python3 tp1/HIT3/client_a.py
```

A saluda a B y queda en espera (simulando un proceso activo).

### 3. Probar la robustez de B

Matá el proceso A con `Ctrl+C`. B mostrará:

```
[B] A se desconecto abruptamente: ...
[B] Conexion con A cerrada. Esperando nueva conexion...
```

B sigue corriendo. Si se levanta una nueva instancia de A, se va a ver que B la atiende
normalmente.

## Decisiones de Diseño

- **`listen(5)`**: se aumenta el backlog a 5 para que el SO pueda encolar conexiones
  entrantes mientras B procesa la actual (útil si varios A intentan conectarse seguido).
  
- **`BrokenPipeError` y `ConnectionResetError`**: cubren los dos escenarios principales
  de desconexión abrupta — escritura en socket cerrado y reset por el par remoto,
  respectivamente.
