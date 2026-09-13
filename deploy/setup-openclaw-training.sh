#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="${ROOT_DIR}/deploy/openclaw-training-automation.sh"

job_id() {
  local name="$1"
  openclaw cron list --all --json | python3 -c 'import json,sys; name=sys.argv[1]; data=json.load(sys.stdin); jobs=data.get("jobs", data if isinstance(data,list) else []); print(next((str(j.get("id","")) for j in jobs if j.get("name")==name), ""))' "$name"
}

reconcile_cron() {
  local name="$1" schedule="$2" action="$3" id
  id="$(job_id "$name")"
  argv="[\"${RUNNER}\",\"${action}\"]"
  if [[ -n "$id" ]]; then
    openclaw cron edit "$id" --cron "$schedule" --tz Asia/Tokyo --exact --command-argv "$argv" --no-deliver --enable
  else
    openclaw cron add --name "$name" --cron "$schedule" --tz Asia/Tokyo --exact --command-argv "$argv" --no-deliver
  fi
}

reconcile_cron chili-training-morning '0 6 * * *' morning
reconcile_cron chili-training-evening '0 20 * * *' evening

# The daily webpage replaces the old free-text Telegram wellbeing question.
legacy_checkin_id="$(job_id chili-evening-check-in)"
if [[ -n "$legacy_checkin_id" ]]; then
  openclaw cron rm "$legacy_checkin_id"
fi

dispatcher_id="$(job_id chili-training-reminders)"
dispatcher_argv="[\"${RUNNER}\",\"dispatch\"]"
if [[ -n "$dispatcher_id" ]]; then
  openclaw cron edit "$dispatcher_id" --every 5m --command-argv "$dispatcher_argv" --no-deliver --enable
else
  openclaw cron add --name chili-training-reminders --every 5m --command-argv "$dispatcher_argv" --no-deliver
fi
