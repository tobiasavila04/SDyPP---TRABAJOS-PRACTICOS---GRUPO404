# HIT #1 - Procesamiento Distribuido de Imágenes (Filtro Sobel)

Este directorio contiene la implementación del algoritmo de detección de bordes (Filtro Sobel) en dos modalidades: centralizada y distribuida. El objetivo es demostrar cómo una arquitectura basada en microservicios y colas de mensajes puede acelerar el procesamiento de tareas pesadas y proveer tolerancia a fallos.

## Requisitos y Configuración General

1. **RabbitMQ Activo:** Asegúrese de tener el broker de mensajería corriendo.
   ```bash
   docker start rabbitmq
   ```
2. **Entorno Virtual Compartido:** Se utiliza un único entorno virtual en la raíz de `HIT_1` para todos los scripts.
   ```bash
   cd HIT_1
   python3 -m venv venv
   source venv/bin/activate
   pip install opencv-python numpy pika
   ```
3. **Imagen de Prueba:** Se requiere una imagen pesada (ej. 1920x1080) llamada `imagen_prueba.jpg` dentro de las carpetas `parte_1_centralizado/` y `parte_2_distribuido/`.

---

## Parte 1: Procesamiento Centralizado
* **Ubicación:** `parte_1_centralizado/`
* **Funcionamiento:** Un único script de Python (`sobel_local.py`) carga la imagen completa, aplica las transformaciones matemáticas del filtro Sobel (ejes X e Y) utilizando OpenCV, y guarda el resultado.
* **Objetivo:** Establecer una métrica de tiempo de procesamiento (línea base) en un solo núcleo para comparar con la versión distribuida.
* **Ejecución:**
  ```bash
  cd parte_1_centralizado
  python sobel_local.py
  ```

---

## Parte 2: Arquitectura Distribuida (Granja de Trabajadores)
* **Ubicación:** `parte_2_distribuido/`
* **Componentes del Sistema:**
  * **Splitter (Maestro):** Corta la imagen original en franjas horizontales (chunks), las codifica en formato Base64 y las publica en la cola `tareas_sobel`.
  * **Workers (Docker):** Contenedores independientes que consumen los chunks, aplican el filtro matemático y envían el resultado a la cola `resultados_sobel`.
  * **Joiner (Recolector):** Lee los chunks procesados, los ensambla en el orden correcto utilizando `numpy.vstack`, guarda la imagen final y calcula el tiempo total de la operación.

### Instrucciones de Ejecución

**Paso 1: Construir la imagen Docker del Worker**
*(Solo es necesario ejecutarlo la primera vez).*
```bash
cd parte_2_distribuido/worker
docker build -t sobel-worker .
```

**Paso 2: Orquestar el Sistema**
Abra tres terminales. Asegúrese de activar el entorno virtual (`source venv/bin/activate`) en la Terminal 1 y 3.

```bash
# Terminal 1: Iniciar el Joiner (se quedará escuchando la cola de resultados)
cd parte_2_distribuido
python joiner.py

# Terminal 2: Levantar los Workers (ej. 2 nodos) conectados a la red del host
docker run -d --name worker1 --net host -e RABBIT_HOST=localhost sobel-worker
docker run -d --name worker2 --net host -e RABBIT_HOST=localhost sobel-worker

# Terminal 3: Iniciar el Splitter para inyectar el trabajo a la cola
cd parte_2_distribuido
python splitter.py
```

---

## Análisis y Tolerancia a Fallos
Esta implementación permite comprobar dos conceptos críticos de la materia:
1. **Escalabilidad y Overhead:** Al aumentar la cantidad de workers de 2 a 4, el tiempo de procesamiento disminuye significativamente (ej. de 0.22s a 0.15s). Sin embargo, la mejora no es 100% lineal debido a la sobrecarga (overhead) que implica codificar, transmitir por red y decodificar los datos.
2. **Resiliencia (Failover):** Gracias al uso de acuses de recibo manuales (`auto_ack=False`), si un contenedor worker es interrumpido abruptamente (`docker kill worker1`) mientras procesa una imagen, RabbitMQ detecta la pérdida de la conexión TCP y reasigna automáticamente esa porción de la imagen a otro worker disponible, garantizando que el `joiner` pueda ensamblar la imagen completa sin pérdida de datos.