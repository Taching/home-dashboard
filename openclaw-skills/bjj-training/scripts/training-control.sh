#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ENV="$(cd -- "${SCRIPT_DIR}/../../../" && pwd)/.env"
ENV_FILE="${CHILI_DASHBOARD_ENV:-$PROJECT_ENV}"
if [[ -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    case "$line" in
      DASHBOARD_AUTOMATION_TOKEN=*)
        value="${line#DASHBOARD_AUTOMATION_TOKEN=}"
        value="${value%%[[:space:]]#*}"
        value="${value#\"}"; value="${value%\"}"
        : "${DASHBOARD_AUTOMATION_TOKEN:=$value}"
        ;;
      CHILI_DASHBOARD_URL=*)
        value="${line#CHILI_DASHBOARD_URL=}"
        value="${value%%[[:space:]]#*}"
        value="${value#\"}"; value="${value%\"}"
        : "${CHILI_DASHBOARD_URL:=$value}"
        ;;
    esac
  done < "$ENV_FILE"
fi

BASE_URL="${CHILI_DASHBOARD_URL:-http://127.0.0.1:8080}"
TOKEN="${DASHBOARD_AUTOMATION_TOKEN:-}"
ACTION="${1:-}"
shift || true
[[ -n "$TOKEN" ]] || { echo "DASHBOARD_AUTOMATION_TOKEN is not set" >&2; exit 1; }

auth=(-H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json")
escape_json() { local value="${1:-}"; value="${value//\\/\\\\}"; value="${value//\"/\\\"}"; printf '%s' "$value"; }

case "$ACTION" in
  today|tomorrow|week)
    curl -fsS "${BASE_URL}/api/v1/training/overview"
    ;;
  plan)
    curl -fsS "${BASE_URL}/api/v1/training/templates/${1:?workout type required}"
    ;;
  start|complete|partial|skip)
    session_id="${1:?session id required}"; note="$(escape_json "${2:-}")"
    status="$ACTION"; [[ "$ACTION" == "start" ]] && status="in_progress"; [[ "$ACTION" == "complete" ]] && status="completed"
    curl -fsS -X PATCH "${BASE_URL}/api/v1/automation/training/sessions/${session_id}" "${auth[@]}" \
      -d "{\"status\":\"${status}\",\"notes\":\"${note}\"}"
    ;;
  move)
    curl -fsS -X PATCH "${BASE_URL}/api/v1/automation/training/sessions/${1:?session id required}" "${auth[@]}" \
      -d "{\"start_at\":\"${2:?ISO datetime required}\"}"
    ;;
  replace|recovery)
    session_id="${1:?session id required}"; workout_type="${2:-recovery}"
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/training/sessions/${session_id}/replace" "${auth[@]}" \
      -d "{\"workout_type\":\"${workout_type}\"}"
    ;;
  add-bjj)
    hard=false; [[ "${2:-normal}" == "hard" ]] && hard=true
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/training/bjj" "${auth[@]}" \
      -d "{\"start_at\":\"${1:?ISO datetime required}\",\"hard\":${hard}}"
    ;;
  metrics)
    curl -fsS -X PATCH "${BASE_URL}/api/v1/automation/training/sessions/${1:?session id required}" "${auth[@]}" \
      -d "{\"metrics\":${2:?metrics JSON required}}"
    ;;
  *)
    echo "Usage: $0 {today|tomorrow|week|plan|start|complete|partial|skip|move|replace|recovery|add-bjj|metrics}" >&2
    exit 2
    ;;
esac
echo
