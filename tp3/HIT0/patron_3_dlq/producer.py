import pika
import json
import time

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# 1. Declaramos el Exchange para mensajes muertos y su respectiva cola
channel.exchange_declare(exchange='dlx_exchange', exchange_type='direct')
channel.queue_declare(queue='cola_muertos')
channel.queue_bind(exchange='dlx_exchange', queue='cola_muertos', routing_key='muertos_key')

# 2. Declaramos la cola principal y la "atamos" a la DLX
# Esto le dice a RabbitMQ: "Si algo falla acá, mandalo al dlx_exchange"
argumentos = {
    'x-dead-letter-exchange': 'dlx_exchange',
    'x-dead-letter-routing-key': 'muertos_key'
}
channel.queue_declare(queue='cola_principal', arguments=argumentos)

print(" Enviando tareas de prueba...")

# Armamos 4 tareas, la 2 y la 4 vienen con el campo de error activado
tareas = [
    {"id": 1, "tarea": "Procesar foto A", "error": False},
    {"id": 2, "tarea": "Procesar foto B", "error": True}, 
    {"id": 3, "tarea": "Procesar foto C", "error": False},
    {"id": 4, "tarea": "Procesar foto D", "error": True}
]

for tarea in tareas:
    mensaje = json.dumps(tarea)
    channel.basic_publish(exchange='', routing_key='cola_principal', body=mensaje)
    print(f" [x] Enviado: {mensaje}")
    time.sleep(0.5)

connection.close()