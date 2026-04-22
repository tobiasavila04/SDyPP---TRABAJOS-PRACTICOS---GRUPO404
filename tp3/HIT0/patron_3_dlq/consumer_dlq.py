import pika

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declaramos la cola de muertos
channel.queue_declare(queue='cola_muertos')

def callback(ch, method, properties, body):
    print(f" [DLQ-ALERTA] Rescatando mensaje fallido de la DLQ: {body.decode()}")
    # Lo marcamos como leído en la DLQ para que desaparezca
    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_consume(queue='cola_muertos', on_message_callback=callback, auto_ack=False)

print(' [!] Monitor de DLQ iniciado. Esperando desastres...')
channel.start_consuming()