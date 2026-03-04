FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY ocbridge /app/ocbridge
CMD ["python", "-m", "ocbridge.bridge_daemon", "--nats", "nats://nats:4222"]
