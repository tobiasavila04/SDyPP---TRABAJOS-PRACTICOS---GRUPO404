# HIT 1 — Orquestador con Containers Efímeros

## Descripción

Sistema cliente-servidor donde un servidor orquestador recibe tareas matemáticas y delega su ejecución a containers Docker efímeros. Cada tarea genera un container nuevo que se destruye al finalizar.

## Arquitectura

```
Cliente  ──POST /task──▶  Servidor (Flask :5000)
                              │
                              ├── docker run (container efímero)
                              │       └── servidorTarea.py (:8080)
                              │               ├── /health
                              │               └── /run
                              │
                              ├── POST /run al container
                              ├── Recibe resultado
                              └── docker stop + rm (limpieza)
```

## Archivos

| Archivo | Descripción |
|---|---|
| `server.py` | Servidor orquestador Flask (puerto 5000). Recibe tareas, crea containers efímeros, envía la tarea y devuelve el resultado. |
| `servidorTarea.py` | Servicio worker que corre dentro de cada container Docker (puerto 8080). Ejecuta las operaciones matemáticas. |
| `client.py` | Cliente CLI que envía tareas al servidor. |
| `Dockerfile` | Imagen Docker para el servicio de tareas (`servidorTarea.py`). |
| `requirements.txt` | Dependencias Python. |

## Operaciones soportadas

- `suma` — Suma todos los valores.
- `resta` — Resta los valores sucesivos al primero.
- `multiplicacion` — Multiplica todos los valores.
- `division` — Divide sucesivamente (con validación de división por cero).

## Uso

### 1. Construir la imagen Docker

```bash
docker build -t tobiasavila142/servicio-tareas:latest .
```

### 2. Iniciar el servidor

```bash
python server.py
```

### 3. Enviar tareas desde el cliente

```bash
# Local
python client.py --operacion suma --valores 10 20 30

# Servidor remoto (AWS)
python client.py --operacion multiplicacion --valores 5 3 2 --remote
```

## Flujo de ejecución

1. El cliente envía un JSON con `operation` y `values` al servidor.
2. El servidor busca un puerto libre y crea un container Docker efímero.
3. Espera a que el container esté listo (health check con reintentos).
4. Envía la tarea al container via `POST /run`.
5. Recibe el resultado y lo retorna al cliente.
6. Elimina el container (stop + rm) en el bloque `finally`.
