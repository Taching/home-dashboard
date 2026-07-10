# openWakeWord currently depends on tflite-runtime, which publishes Linux ARM64
# wheels for Python 3.11 but not 3.12.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends alsa-utils libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY download_openwakeword_resources.py ./
RUN python download_openwakeword_resources.py
COPY worker.py wakeword.py monitor.py ./
COPY tools ./tools

CMD ["python", "worker.py"]
