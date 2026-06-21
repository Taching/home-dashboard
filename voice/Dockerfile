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
RUN python -c "from openwakeword.utils import download_models; download_models(['hey_jarvis_v0.1'])"
COPY worker.py wakeword.py ./

CMD ["python", "worker.py"]
