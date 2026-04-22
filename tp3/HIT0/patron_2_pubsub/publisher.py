import pika
import time
import random

# Conexión a RabbitMQ
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declaramos un Exchange de tipo 'fanout' (transmisión a todos)
# Le ponemos de nombre 'logs_bloques'
channel.exchange_declare(exchange='logs_bloques', exchange_type='fanout')

print(" Empezando a minar bloques...")

for i in range(1, 6):
    # Simulamos el hash de un bloque minado
    hash_bloque = f"0000x{random.randint(1000, 9999)}... bloque #{i}"
    
    # Publicamos en el exchange, el routing_key se ignora en fanout
    channel.basic_publish(exchange='logs_bloques',
                          routing_key='',
                          body=hash_bloque)
    
    print(f" [x] Broadcast emitido: '{hash_bloque}'")
    time.sleep(2)

connection.close()