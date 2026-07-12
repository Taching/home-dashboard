#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:?Usage: $0 path/to/hey_chee_lee.tflite}"
DEST="${ROOT}/assets/voice/hey_chee_lee.tflite"

if [[ ! -f "$SRC" ]]; then
  echo "Source file not found: $SRC" >&2
  exit 1
fi

cp "$SRC" "$DEST"
echo "Installed wake-word model at $DEST"

if command -v docker >/dev/null 2>&1; then
  cd "$ROOT"
  if docker compose -f compose.yaml -f compose.pi.yaml --profile voice ps --status running -q voice 2>/dev/null | grep -q .; then
    DOCKER_API_VERSION="${DOCKER_API_VERSION:-1.41}" \
      docker compose -f compose.yaml -f compose.pi.yaml --profile voice up -d --force-recreate voice
    echo "Voice container restarted."
  else
    echo "Voice container not running — start it when ready."
  fi
fi
