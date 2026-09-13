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
  today)
    day="${1:-$(date +%F)}"
    curl -fsS "${BASE_URL}/api/v1/plan/${day}"
    ;;
  rest-today)
    payload="{\"action\":\"rest_today\""
    if [[ -n "${1:-}" ]]; then payload="${payload},\"day\":\"${1}\""; fi
    payload="${payload}}"
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" -d "${payload}"
    ;;
  move-gym)
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
      -d "{\"action\":\"move_gym\",\"to_date\":\"${1:?date required}\"}"
    ;;
  complete-task)
    value="${1:?task id or title required}"
    if [[ "$value" =~ ^[0-9a-fA-F-]{32,}$ ]]; then
      curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
        -d "{\"action\":\"complete_task\",\"task_id\":\"$(escape_json "$value")\"}"
    else
      curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
        -d "{\"action\":\"complete_task\",\"task_title\":\"$(escape_json "$value")\"}"
    fi
    ;;
  move-meeting)
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
      -d "{\"action\":\"move_meeting\",\"event_id\":\"$(escape_json "${1:?event id required}")\",\"start_at\":\"${2:?ISO datetime required}\"}"
    ;;
  replan)
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" -d '{"action":"replan"}'
    ;;
  fatigue)
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
      -d "{\"action\":\"fatigue\",\"day\":\"${1:?date required}\",\"fatigue_state\":\"${2:?state required}\"}"
    ;;
  confirm-bjj)
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
      -d "{\"action\":\"confirm_bjj\",\"day\":\"${1:?date required}\"}"
    ;;
  decline-bjj)
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
      -d "{\"action\":\"decline_bjj\",\"day\":\"${1:?date required}\"}"
    ;;
  gym-today)
    curl -fsS -X POST "${BASE_URL}/api/v1/automation/plan" "${auth[@]}" \
      -d "{\"action\":\"gym_today\",\"day\":\"${1:?date required}\",\"workout_type\":\"${2:?strength_a or strength_b required}\"}"
    ;;
  *)
    echo "Usage: $0 {today|rest-today|move-gym|complete-task|move-meeting|fatigue|confirm-bjj|decline-bjj|gym-today|replan}" >&2
    exit 2
    ;;
esac
echo
