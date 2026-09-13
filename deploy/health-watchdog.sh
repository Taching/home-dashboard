#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="${CHILI_PROJECT_DIR:-/home/takatoshi/Work/home-dashboard}"
BASE_URL="${CHILI_DASHBOARD_URL:-http://127.0.0.1:8080}"
STATE_DIR="${CHILI_WATCHDOG_STATE_DIR:-/run/chili-health-watchdog}"
FAILURE_THRESHOLD="${CHILI_WATCHDOG_FAILURE_THRESHOLD:-2}"
COOLDOWN_SECONDS="${CHILI_WATCHDOG_COOLDOWN_SECONDS:-900}"
RECOVERY_WAIT_SECONDS="${CHILI_WATCHDOG_RECOVERY_WAIT_SECONDS:-10}"
COMPOSE=(
  docker compose
  -f compose.yaml
  -f compose.pi.yaml
  -f compose.apple-calendar-bridge.yaml
  --profile walkingpad
)

cd "$PROJECT_DIR" || exit 1
mkdir -p "$STATE_DIR" || exit 1

log() {
  printf 'watchdog: %s\n' "$*"
}

state_value() {
  local path="$STATE_DIR/$1"
  local value=0
  if [[ -r "$path" ]]; then
    read -r value < "$path" || value=0
  fi
  [[ "$value" =~ ^[0-9]+$ ]] || value=0
  printf '%s' "$value"
}

set_state() {
  printf '%s\n' "$2" > "$STATE_DIR/$1"
}

reset_failures() {
  set_state "$1.failures" 0
}

register_failure() {
  local key="$1"
  local count
  count="$(state_value "$key.failures")"
  count=$((count + 1))
  set_state "$key.failures" "$count"
  printf '%s' "$count"
}

cooldown_ready() {
  local key="$1"
  local now last elapsed
  now="$(date +%s)"
  last="$(state_value "$key.recovered_at")"
  if (( last == 0 || last > now )); then
    return 0
  fi
  elapsed=$((now - last))
  (( elapsed >= COOLDOWN_SECONDS ))
}

mark_recovery() {
  set_state "$1.recovered_at" "$(date +%s)"
}

dashboard_healthy() {
  curl -fsS --max-time 10 "${BASE_URL}/api/v1/health" >/dev/null
}

service_running() {
  local service="$1"
  "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -Fxq "$service"
}

threshold_reached() {
  local key="$1"
  local label="$2"
  local count
  count="$(register_failure "$key")"
  log "$label failed check $count/$FAILURE_THRESHOLD"
  (( count >= FAILURE_THRESHOLD )) || return 1
  if ! cooldown_ready "$key"; then
    log "$label recovery suppressed by ${COOLDOWN_SECONDS}s cooldown"
    return 1
  fi
  return 0
}

overall_status=0

# A successful HTTP response proves that both nginx and the backend proxy path
# are responding. Recover stopped containers with `up`; restart running but
# unresponsive containers. Never rebuild images from the watchdog.
if dashboard_healthy; then
  reset_failures dashboard
else
  if threshold_reached dashboard "Dashboard HTTP"; then
    log "recovering dashboard frontend and backend"
    if service_running backend && service_running frontend; then
      if ! "${COMPOSE[@]}" restart --no-deps backend frontend; then
        log "dashboard restart command failed"
        overall_status=1
      fi
    elif ! "${COMPOSE[@]}" up -d --no-build backend frontend; then
      log "dashboard start command failed"
      overall_status=1
    fi
    mark_recovery dashboard
    sleep "$RECOVERY_WAIT_SECONDS"
    if dashboard_healthy; then
      log "dashboard HTTP recovered"
      reset_failures dashboard
    else
      log "dashboard HTTP is still unavailable after recovery"
      overall_status=1
    fi
  fi
fi

ensure_compose_service() {
  local service="$1"
  local label="$2"
  if service_running "$service"; then
    reset_failures "$service"
    return
  fi
  if ! threshold_reached "$service" "$label"; then
    return
  fi
  log "starting $label"
  if "${COMPOSE[@]}" up -d --no-build "$service"; then
    mark_recovery "$service"
    reset_failures "$service"
    log "$label start requested"
  else
    mark_recovery "$service"
    log "$label start failed"
    overall_status=1
  fi
}

ensure_compose_service calendar-bridge "Calendar bridge"

# A powered-off WalkingPad is normal; only its collector process is monitored,
# and only when the integration is configured.
if grep -Eq '^WALKINGPAD_BLE_NAME=.+$' .env \
  && grep -Eq '^WALKINGPAD_BRIDGE_TOKEN=.+$' .env; then
  ensure_compose_service walkingpad-collector "WalkingPad collector"
fi

# Chromium is outside Compose. Only monitor it once the graphical target is up,
# so boot-time display initialization cannot create a false failure.
if systemctl is-active --quiet graphical.target; then
  if systemctl is-active --quiet chili-kiosk.service; then
    reset_failures kiosk
  elif threshold_reached kiosk "Chromium kiosk"; then
    log "restarting Chromium kiosk service"
    if systemctl restart chili-kiosk.service; then
      mark_recovery kiosk
      reset_failures kiosk
      log "Chromium kiosk restart requested"
    else
      mark_recovery kiosk
      log "Chromium kiosk restart failed"
      overall_status=1
    fi
  fi
fi

exit "$overall_status"
