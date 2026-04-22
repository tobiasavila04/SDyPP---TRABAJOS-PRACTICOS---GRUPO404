# Usamos una imagen de Python liviana
FROM python:3.11-slim

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos las dependencias y las instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código del worker
COPY worker.py .

# Ejecutamos el script al arrancar
CMD python worker.py
