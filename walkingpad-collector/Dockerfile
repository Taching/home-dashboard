FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bluez dbus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir "walkingpad-controller>=0.4.11" "bleak>=0.22,<2.0" "httpx>=0.27,<1.0"

COPY collector ./collector
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "collector.main"]
