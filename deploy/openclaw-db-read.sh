#!/usr/bin/env bash
set -euo pipefail

# Read date-scoped dashboard SQLite snapshot (for OpenClaw / host scripts).
#
# Usage:
#   deploy/openclaw-db-read.sh 2026-07-13
#   deploy/openclaw-db-read.sh 2026-07-07 days=7
#   deploy/openclaw-db-read.sh 2026-07-01 end=2026-07-31
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

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 YYYY-MM-DD [days=N|end=YYYY-MM-DD]" >&2
  exit 1
fi

DAY="$1"
QUERY=""
if [[ $# -ge 2 ]]; then
  QUERY="?$2"
fi

curl -fsS \
  -H "Authorization: Bearer ${TOKEN}" \
  "${BASE_URL}/api/v1/db/${DAY}${QUERY}"
echo
