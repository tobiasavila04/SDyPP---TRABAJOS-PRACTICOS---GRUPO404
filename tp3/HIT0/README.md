# HIT #0 - Patrones de Mensajería con RabbitMQ

Este directorio contiene la implementación de los cuatro patrones fundamentales de mensajería requeridos para comprender el funcionamiento de RabbitMQ antes de avanzar con el procesamiento distribuido de imágenes.

## Requisitos y Configuración

Para ejecutar estos ejemplos, es necesario contar con un broker de RabbitMQ activo y las librerías de Python configuradas.

1. **Levantar RabbitMQ (Docker):**
   ```bash
   docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:management
   ```
2. **Entorno de Python:**
   Asegúrese de ejecutar los scripts dentro de un entorno virtual para no interferir con los paquetes del sistema.
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install pika
   ```

---

## Patrones Implementados

### 1. Message Queue (Punto a Punto)
* **Ubicación:** `patron_1_queue/`
* **Funcionamiento:** Un productor envía 10 tareas numeradas a una cola. Al levantar dos consumidores, RabbitMQ distribuye los mensajes de forma equitativa utilizando el algoritmo **Round-Robin**.
* **Uso:** Ideal para distribuir carga de trabajo donde cada tarea debe ser procesada exactamente por un solo worker.
* **Ejecución:**
  Abra tres terminales. En las dos primeras inicie los workers, y en la tercera envíe los mensajes:
  ```bash
  # Terminal 1 y 2
  python patron_1_queue/consumer.py
  
  # Terminal 3
  python patron_1_queue/producer.py
  ```

### 2. Pub/Sub (Fan-out)
* **Ubicación:** `patron_2_pubsub/`
* **Funcionamiento:** Utiliza un exchange de tipo `fanout`. El publicador emite eventos de "nuevo bloque minado" y todos los nodos conectados reciben una copia idéntica del mensaje simultáneamente.
* **Uso:** Implementado en la industria para notificaciones masivas o sincronización de estados.
* **Ejecución:**
  Abra varias terminales para los suscriptores y una final para el publicador:
  ```bash
  # Terminales 1, 2 y 3 (Suscriptores)
  python patron_2_pubsub/subscriber.py
  
  # Terminal 4 (Publicador)
  python patron_2_pubsub/publisher.py
  ```

### 3. Dead Letter Queue (DLQ)
* **Ubicación:** `patron_3_dlq/`
* **Funcionamiento:** Configura una cola principal vinculada a una **Dead Letter Exchange (DLX)**. Si el consumidor principal rechaza un mensaje (`nack`) debido a un error, RabbitMQ lo redirige a la cola de Dead Letters para que un segundo consumidor lo audite.
* **Uso:** Patrón fundamental para la resiliencia, evitando la pérdida de mensajes fallidos.
* **Ejecución:**
  Respete este orden estricto de ejecución en tres terminales:
  ```bash
  # Terminal 1 (Monitor de fallos)
  python patron_3_dlq/consumer_dlq.py
  
  # Terminal 2 (Worker principal)
  python patron_3_dlq/consumer_main.py
  
  # Terminal 3 (Inyector de tareas)
  python patron_3_dlq/producer.py
  ```

### 4. Retry con Exponential Backoff
* **Ubicación:** `patron_4_retry/`
* **Funcionamiento:** Si el procesamiento falla (probabilidad simulada), el mensaje se reencola con un retardo creciente (1s, 2s, 4s, 8s) utilizando el concepto de TTL. Tras 4 reintentos, se envía a la DLQ.
* **Uso:** Estándar de la industria para manejar fallos transitorios como servicios caídos o timeouts.
* **Ejecución:**
  Abra dos terminales. El worker procesará e intentará recuperar los errores automáticamente:
  ```bash
  # Terminal 1
  python patron_4_retry/consumer_retry.py
  
  # Terminal 2 (Puede ejecutarlo varias veces)
  python patron_4_retry/producer.py
  ```