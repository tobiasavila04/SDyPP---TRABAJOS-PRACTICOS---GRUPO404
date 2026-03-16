# HIT #7 - Sistema de Inscripciones

## Descripción

Extiende el HIT #6 con un sistema de **ventanas de tiempo de 1 minuto** coordinado por D.

**Regla central**: cuando C se inscribe a las 11:28:34, queda anotado para la ventana
de las 11:29. Solo cuando el reloj llega a las 11:29:00 esa inscripción se activa y C
pasa a ser visible para los nuevos C que lleguen. Mientras tanto, C solo ve los peers
de la ventana **actual** (11:28), no los de la próxima.

D mantiene dos listas:
- `current_window` → nodos activos, visibles para los C que se inscriben ahora.
- `next_window` → inscripciones pendientes para la próxima ventana.

Cada 60 s (al cambio de minuto): `current = next`, `next = []`, y la ventana que cierra
se persiste en `inscripciones.json`.

## Diagrama de ventanas

```
Tiempo  │  next_window          current_window     Accion de C al inscribirse
────────┼────────────────────────────────────────────────────────────────────
11:28   │  [C1, C2]             []                 C1, C2 → 0 peers (current vacío)
        │                                          C1 y C2 no se ven entre sí aún
────────┼── TICK 11:29 ─────────────────────────────────────────────────────
11:29   │  [C3]                 [C1, C2]           C3 → 2 peers (C1 y C2) ✓
        │                                          C3 saluda a C1 y C2
────────┼── TICK 11:30 ─────────────────────────────────────────────────────
11:30   │  []                   [C3]               ...
```

## Persistencia — `inscripciones.json`

Cada vez que cierra una ventana, D guarda su contenido:

```json
[
  {
    "window_start": "2026-03-15T11:29:00+00:00",
    "window_end":   "2026-03-15T11:30:00+00:00",
    "node_count": 2,
    "nodes": [
      { "host": "10.0.0.1", "port": 54321, "registered_at": "..." },
      { "host": "10.0.0.2", "port": 54322, "registered_at": "..." }
    ]
  }
]
```

## Endpoints HTTP de Node D

| Método | Ruta              | Descripción                                       |
|--------|-------------------|---------------------------------------------------|
| GET    | `/health`         | Uptime, info de ventana actual y próxima          |
| GET    | `/window/current` | Nodos activos en la ventana actual                |
| GET    | `/window/next`    | Nodos inscriptos para la próxima ventana          |
| GET    | `/windows`        | Historial completo desde `inscripciones.json`     |
| DELETE | `/windows`        | Limpia estado en memoria y archivo (testing)      |

### Ejemplo `/health`

```json
{
  "status": "healthy",
  "uptime_seconds": 183.4,
  "current_window": { "start": "2026-03-15T11:29:00+00:00", "node_count": 2 },
  "next_window":    { "start": "2026-03-15T11:30:00+00:00", "node_count": 1 }
}
```

## Cómo ejecutar

### 1. Iniciar Node D

```bash
uvicorn tp1.HIT7.node_d:app --host 0.0.0.0 --port 8080
```

### 2. Inscribir nodos C

```bash
# Ventana 1: C1 y C2 se inscriben (van a next_window)
python3 tp1/HIT7/node_c.py --registry-host 127.0.0.1 --registry-port 9000
python3 tp1/HIT7/node_c.py --registry-host 127.0.0.1 --registry-port 9000

# Esperar el cambio de minuto (~60s)
# Ventana 2: C3 se inscribe y ve a C1/C2 como peers actuales
python3 tp1/HIT7/node_c.py --registry-host 127.0.0.1 --registry-port 9000
```

### 3. Consultar estado

```bash
curl http://localhost:8080/health
curl http://localhost:8080/window/current
curl http://localhost:8080/window/next
curl http://localhost:8080/windows
```

## Decisiones de Diseño

- **`_window_manager` basado en polling cada 1 s**: compara el minuto actual con el
  anterior. Es más simple y robusto que calcular un sleep hasta el próximo minuto
  exacto (que podría derivar por el scheduler del SO).
- **Dos listas separadas + lock**: `_current_window` y `_next_window` comparten un
  único `threading.Lock`. La rotación es atómica: se reemplazan ambas listas dentro
  del bloque `with _lock`.
- **C recibe peers de `current_window`, no de `next_window`**: los nodos no saben a 
  priori quiénes son sus pares para la próxima ventana.
- **Persistencia append-only**: se agrega una entrada por ventana cerrada. Nunca se
  sobreescriben entradas anteriores, lo que facilita auditar el historial de ejecuciones.
- **`INSCRIPCIONES_FILE` configurable por env var**: permite cambiar la ruta del archivo
  sin modificar el código (útil en EC2 para escribir en un directorio con permisos).
