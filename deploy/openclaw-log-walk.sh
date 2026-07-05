#!/usr/bin/env bash
set -euo pipefail

# Log a manual walk session on the dashboard (for OpenClaw or host scripts).
#
# Usage:
#   deploy/openclaw-log-walk.sh 30 2
#   deploy/openclaw-log-walk.sh "walked 30 min and 2 km today"
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
  echo "Usage: $0 <minutes> <km> | \"walk message\"" >&2
  exit 1
fi

if [[ $# -eq 1 ]]; then
  payload=$(python3 - <<PY
import json, sys
print(json.dumps({"message": sys.argv[1]}))
PY
"$1")
else
  payload=$(python3 - <<PY
import json, sys
print(json.dumps({"duration_minutes": float(sys.argv[1]), "distance_km": float(sys.argv[2])}))
PY
"$1" "$2")
fi

curl -fsS -X POST "${BASE_URL}/api/v1/automation/walkingpad/log" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${payload}"

echo
