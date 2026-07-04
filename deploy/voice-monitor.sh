#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8080}"
export BACKEND_URL

if docker compose -f "$ROOT/compose.yaml" ps voice --status running -q 2>/dev/null | grep -q .; then
  exec docker compose -f "$ROOT/compose.yaml" exec -T \
    -e BACKEND_URL=http://backend:8000 \
    voice python monitor.py --url http://backend:8000
fi

VENV="$ROOT/voice/.venv"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -r "$ROOT/voice/requirements.txt"
exec "$VENV/bin/python" "$ROOT/voice/monitor.py" --url "$BACKEND_URL"
