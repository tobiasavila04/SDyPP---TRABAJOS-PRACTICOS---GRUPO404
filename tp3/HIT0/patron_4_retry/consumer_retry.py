import pika
import random

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# 1. Cola principal y Cola de muertos (DLQ)
channel.queue_declare(queue='cola_principal_retry')
channel.queue_declare(queue='cola_muertos')

# 2. Cola de espera (Intermedia)
# Si un mensaje muere acá por viejo (TTL), lo manda de vuelta a la cola_principal
argumentos_espera = {
    'x-dead-letter-exchange': '',
    'x-dead-letter-routing-key': 'cola_principal_retry'
}
channel.queue_declare(queue='cola_espera', arguments=argumentos_espera)

def callback(ch, method, properties, body):
    tarea = body.decode()
    
    # Obtenemos la cantidad de intentos actuales desde los headers
    headers = properties.headers or {}
    intentos_actuales = headers.get('retry_count', 0)
    
    print(f" \n--- Procesando '{tarea}' (Intento {intentos_actuales + 1}) ---")
    
    # Simulamos un 50% de probabilidad de fallo
    fallo_simulado = random.random() < 0.5
    
    if fallo_simulado:
        print(" [X] Error al procesar la tarea.")
        
        if intentos_actuales >= 4:
            print(" [DLQ] Límite de 4 reintentos alcanzado. Mandando a la DLQ definitiva.")
            ch.basic_publish(exchange='', routing_key='cola_muertos', body=body)
        else:
            intentos_actuales += 1
            # Calculamos el delay: 2 elevado a la (intentos-1) -> 1, 2, 4, 8
            delay_segundos = 2 ** (intentos_actuales - 1)
            delay_ms = delay_segundos * 1000
            
            print(f" [!] Reencolando. Esperando {delay_segundos} segundos...")
            
            # Actualizamos el contador y mandamos a la cola de espera con un TTL
            nuevas_propiedades = pika.BasicProperties(
                headers={'retry_count': intentos_actuales},
                expiration=str(delay_ms) # El TTL en milisegundos
            )
            ch.basic_publish(exchange='', routing_key='cola_espera', body=body, properties=nuevas_propiedades)
            
    else:
        print(" [V] ¡Éxito! Tarea procesada correctamente.")
    
    # Siempre hacemos ACK al mensaje original, porque o bien lo procesamos, 
    # o lo mandamos a la cola de espera, o a la DLQ. Ya no pertenece a esta cola.
    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_consume(queue='cola_principal_retry', on_message_callback=callback, auto_ack=False)

print(' [*] Worker de reintentos iniciado. Esperando tareas...')
channel.start_consuming()