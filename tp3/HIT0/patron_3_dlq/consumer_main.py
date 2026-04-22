import pika
import json
import time

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Volvemos a declarar la cola principal por las dudas
argumentos = {'x-dead-letter-exchange': 'dlx_exchange', 'x-dead-letter-routing-key': 'muertos_key'}
channel.queue_declare(queue='cola_principal', arguments=argumentos)

def callback(ch, method, properties, body):
    datos = json.loads(body.decode())
    
    if datos.get("error") == True:
        print(f" [X] ERROR fatal en la tarea {datos['id']}. Rechazando...")
        # ch.basic_nack con requeue=False manda el mensaje a la DLQ
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    else:
        print(f" [v] Tarea {datos['id']} procesada correctamente.")
        time.sleep(1)
        # ch.basic_ack confirma que terminamos bien
        ch.basic_ack(delivery_tag=method.delivery_tag)

# OJO: auto_ack=False es obligatorio para poder hacer ack/nack manuales
channel.basic_consume(queue='cola_principal', on_message_callback=callback, auto_ack=False)

print(' [*] Worker principal esperando tareas...')
channel.start_consuming()