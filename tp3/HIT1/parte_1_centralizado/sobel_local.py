import cv2
import numpy as np
import time
import os

print("--- Iniciando Procesamiento Centralizado de Sobel ---")

# Ruta de la imagen (asegurate de tenerla en la misma carpeta)
nombre_imagen = 'imagen_prueba.jpg'

if not os.path.exists(nombre_imagen):
    print(f"Error: No se encontró '{nombre_imagen}'.")
    exit()

# 1. Iniciar el cronómetro
start_time = time.time()

# 2. Cargar la imagen directamente en escala de grises (Sobel trabaja sobre intensidades)
imagen = cv2.imread(nombre_imagen, cv2.IMREAD_GRAYSCALE)

# 3. Aplicar el filtro Sobel
# Calculamos las derivadas en el eje X y en el eje Y. 
# Usamos cv2.CV_64F (float de 64 bits) para no perder datos si los valores son negativos
sobel_x = cv2.Sobel(imagen, cv2.CV_64F, 1, 0, ksize=3)
sobel_y = cv2.Sobel(imagen, cv2.CV_64F, 0, 1, ksize=3)

# 4. Unificar ambos ejes usando la magnitud del vector (Pitágoras básico)
sobel_combinado = cv2.magnitude(sobel_x, sobel_y)

# 5. Normalizar el resultado
# Los valores pueden salirse del rango 0-255 de los píxeles, así que lo forzamos
sobel_normalizado = np.uint8(np.absolute(sobel_combinado))

# 6. Parar el cronómetro
end_time = time.time()
tiempo_total = end_time - start_time

# 7. Guardar el resultado
nombre_salida = 'resultado_sobel.jpg'
cv2.imwrite(nombre_salida, sobel_normalizado)

print(f"[V] ¡Proceso terminado con éxito!")
print(f"[*] Imagen guardada como: {nombre_salida}")
print(f"[*] Tiempo de procesamiento: {tiempo_total:.4f} segundos")