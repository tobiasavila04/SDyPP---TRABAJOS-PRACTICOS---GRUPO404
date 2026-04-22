import pika

# Conexión a RabbitMQ
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declaramos el MISMO exchange por si el subscriber arranca primero
channel.exchange_declare(exchange='logs_bloques', exchange_type='fanout')

# Creamos una cola temporal exclusiva para este suscriptor
# RabbitMQ le asignará un nombre aleatorio (ej: amq.gen-JzTY20BRgKO-HjmUJj0wLg)
result = channel.queue_declare(queue='', exclusive=True)
queue_name = result.method.queue

# Atamos (bind) nuestra cola temporal al exchange
channel.queue_bind(exchange='logs_bloques', queue=queue_name)

print(f" [*] Nodo conectado (Cola: {queue_name}). Esperando nuevos bloques...")

def callback(ch, method, properties, body):
    print(f" [x] ¡Notificación recibida! {body.decode()}")

channel.basic_consume(queue=queue_name,
                      auto_ack=True,
                      on_message_callback=callback)

channel.start_consuming()