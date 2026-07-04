#!/usr/bin/env bash
set -euo pipefail

# Morning plant watering for OpenClaw cron (08:00 Asia/Tokyo).
# Install on the Pi host where OpenClaw runs, or call via Tailscale from elsewhere.
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

curl -fsS -X POST "${BASE_URL}/api/v1/automation/water" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json"

echo
