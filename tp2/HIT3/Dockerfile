FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node.py .

EXPOSE 7001 7002 7003

CMD ["python", "node.py"]
