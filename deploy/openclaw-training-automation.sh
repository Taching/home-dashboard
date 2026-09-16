#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ENV="$(cd -- "${SCRIPT_DIR}/.." && pwd)/.env"
if [[ -f "$PROJECT_ENV" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    case "$line" in
      DASHBOARD_AUTOMATION_TOKEN=*) value="${line#*=}"; value="${value%%[[:space:]]#*}"; value="${value#\"}"; value="${value%\"}"; : "${DASHBOARD_AUTOMATION_TOKEN:=$value}" ;;
      CHILI_DASHBOARD_URL=*) value="${line#*=}"; value="${value%%[[:space:]]#*}"; value="${value#\"}"; value="${value%\"}"; : "${CHILI_DASHBOARD_URL:=$value}" ;;
    esac
  done < "$PROJECT_ENV"
fi

ACTION="${1:?morning, evening, or dispatch required}"
case "$ACTION" in morning|evening|dispatch) ;; *) echo "Invalid action" >&2; exit 2 ;; esac
body="$(curl -fsS -X POST "${CHILI_DASHBOARD_URL:-http://127.0.0.1:8080}/api/v1/automation/training/run" \
  -H "Authorization: Bearer ${DASHBOARD_AUTOMATION_TOKEN:?DASHBOARD_AUTOMATION_TOKEN is not set}" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"${ACTION}\"}")"
echo NO_REPLY
python3 -c 'import json,sys
payload=json.loads(sys.stdin.read() or "{}")
status=str(payload.get("status") or "")
notify=payload.get("notify") if isinstance(payload.get("notify"), dict) else {}
if status == "failed" or notify.get("status") == "failed":
    message=payload.get("message") or notify.get("message") or status or "failed"
    raise SystemExit(str(message))
' <<<"$body"
