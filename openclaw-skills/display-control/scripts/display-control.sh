#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ENV="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)/.env"
ENV_FILE="${CHILI_DASHBOARD_ENV:-${CHILI_PLANT_WATER_ENV:-$PROJECT_ENV}}"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    case "$line" in
      DASHBOARD_AUTOMATION_TOKEN=*)
        value="${line#DASHBOARD_AUTOMATION_TOKEN=}"
        value="${value%%[[:space:]]#*}"
        value="${value#\"}"
        value="${value%\"}"
        : "${DASHBOARD_AUTOMATION_TOKEN:=$value}"
        ;;
      CHILI_DASHBOARD_URL=*)
        value="${line#CHILI_DASHBOARD_URL=}"
        value="${value%%[[:space:]]#*}"
        value="${value#\"}"
        value="${value%\"}"
        : "${CHILI_DASHBOARD_URL:=$value}"
        ;;
    esac
  done < "$ENV_FILE"
fi

BASE_URL="${CHILI_DASHBOARD_URL:-http://127.0.0.1:8080}"
TOKEN="${DASHBOARD_AUTOMATION_TOKEN:-}"
ACTION="${1:-}"

case "$ACTION" in
  on|off|status) ;;
  *)
    echo "Usage: $0 {on|off|status}" >&2
    exit 2
    ;;
esac

if [[ -z "$TOKEN" ]]; then
  echo "DASHBOARD_AUTOMATION_TOKEN is not set" >&2
  exit 1
fi

curl -fsS -X POST "${BASE_URL}/api/v1/automation/display" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"${ACTION}\"}"
echo
