#!/usr/bin/env bash
set -euo pipefail

# Log a gym / BJJ / sober check-in on the dashboard (for OpenClaw or host scripts).
# Walks stay on deploy/openclaw-log-walk.sh — do not log them here.
#
# Usage:
#   deploy/openclaw-log-training.sh '{"kind":"strength_a","completed":"yes","feeling":"normal"}'
#   deploy/openclaw-log-training.sh "did Strength A, felt tired"
#
# Required env (e.g. in ~/.config/chili/plant-water.env):
#   DASHBOARD_AUTOMATION_TOKEN=...
# Optional:
#   CHILI_DASHBOARD_URL=http://127.0.0.1:8080

ENV_FILE="${CHILI_PLANT_WATER_ENV:-$HOME/.config/chili/plant-water.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

BASE_URL="${CHILI_DASHBOARD_URL:-http://127.0.0.1:8080}"
TOKEN="${DASHBOARD_AUTOMATION_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  echo "DASHBOARD_AUTOMATION_TOKEN is not set" >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <json-object> | \"training message\"" >&2
  exit 1
fi

if [[ "$1" == "{"* ]]; then
  payload="$1"
else
  payload=$(python3 - <<PY
import json, sys
print(json.dumps({"message": sys.argv[1]}))
PY
"$1")
fi

curl -fsS -X POST "${BASE_URL}/api/v1/automation/training/log" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${payload}"

echo
