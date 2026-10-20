#!/usr/bin/env bash
# Automated UAT verification for Workout library + weekly analyzer V1 (M1–M4).
# Exit 0 = all automated checks passed. Photos/M5 are N/A.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
    PYTHON="$ROOT/backend/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

export DATABASE_URL="${DATABASE_URL:-sqlite://}"
export SENSOR_ENABLED="${SENSOR_ENABLED:-false}"
export TZ="${TZ:-Asia/Tokyo}"
export CHILI_PRODUCTION_MODE="${CHILI_PRODUCTION_MODE:-false}"
export PYTHONPATH="${PYTHONPATH:-backend}"

pass=0
fail=0
na=0

ok() { echo "  PASS  $1"; pass=$((pass + 1)); }
bad() { echo "  FAIL  $1"; fail=$((fail + 1)); }
skip() { echo "  N/A   $1"; na=$((na + 1)); }

echo "=== UAT V1 — Workout library + weekly analyzer ==="
echo "python: $PYTHON"
echo

echo "→ Backend acceptance suites"
if "$PYTHON" -m unittest \
  backend.tests.test_exercise_library \
  backend.tests.test_workout_logging \
  backend.tests.test_rain_handling \
  backend.tests.test_workout_backfill \
  backend.tests.test_weekly_analyzer \
  -q > /tmp/uat-v1-backend.log 2>&1; then
  ok "unittest (exercise library, logging, rain, backfill, weekly analyzer)"
else
  bad "unittest (see /tmp/uat-v1-backend.log)"
  tail -40 /tmp/uat-v1-backend.log | sed 's/^/         /'
fi

echo
echo "→ Static probes (spec boundaries)"

probe() {
  local label="$1" kind="$2" pattern="$3" path="$4"
  local hits
  hits=$(rg -n --glob '!**/node_modules/**' "$pattern" "$path" 2>/dev/null | head -20 || true)
  case "$kind" in
    must)
      if [[ -n "$hits" ]]; then ok "$label"; else bad "$label (pattern not found: $pattern)"; fi
      ;;
    must_not)
      if [[ -z "$hits" ]]; then ok "$label"; else bad "$label (unexpected hits)"; echo "$hits" | sed 's/^/         /'; fi
      ;;
  esac
}

probe "Ask coach API exists (on-demand)" must 'ask-coach|ask_coach' backend/app
probe "Weekly page has Ask coach button" must 'Ask coach about this week' frontend/src/pages/WeeklyReviewPage.tsx
probe "Schedule-change is prefill-only link" must 'schedule-change\?prefill=' frontend/src/pages/WeeklyReviewPage.tsx
probe "Rain three-action wording present" must 'Keep original plan' backend/app/domain/rain_handling.py
probe "requires_travel gates rain check" must 'requires_travel' backend/app/api/training.py
probe "No progress-photo V2 routes on V1" must_not 'progress.photo|progress_photo' backend/app
# Wall/kiosk entry is main.tsx / Dashboard — Ask coach must live on /weekly only
if rg -n 'Ask coach about this week' frontend/src --glob '!**/WeeklyReviewPage.tsx' >/dev/null 2>&1; then
  bad "Ask coach about this week leaked outside WeeklyReviewPage"
else
  ok "Ask coach about this week stays on /weekly only"
fi

# Monday check-in may recompute analyzer; must not call ask_coach automatically
if rg -n 'ask_coach|ask-coach' backend/app/api/daily.py >/dev/null 2>&1; then
  bad "daily.py must not call Ask coach automatically"
else
  ok "Monday/daily path does not call Ask coach"
fi

# Recompute endpoint should be deterministic (no OpenAI in weekly_analyzer)
if rg -n 'openai|httpx\.post|responses' backend/app/domain/weekly_analyzer.py >/dev/null 2>&1; then
  bad "weekly_analyzer.py must stay AI-free"
else
  ok "weekly_analyzer.py is deterministic (no LLM client)"
fi

# Coach module is the only weekly AI entry; dry-run guarded
if rg -n 'is_dry_run|guard_external_call' backend/app/domain/weekly_coach.py >/dev/null 2>&1; then
  ok "weekly_coach.py has dry-run guards"
else
  bad "weekly_coach.py missing dry-run guards"
fi

skip "Photos / M5 (V2 out of scope)"
skip "Pi manual smoke (/training/exercises, /workout, /weekly, rain prompt)"

echo
echo "→ Frontend unit smoke (scoped)"
if [[ -d frontend/node_modules ]]; then
  if (cd frontend && npm test >/tmp/uat-v1-frontend.log 2>&1); then
    ok "frontend npm test"
  else
    bad "frontend npm test (see /tmp/uat-v1-frontend.log)"
  fi
else
  echo "  SKIP  frontend npm test (no node_modules; run npm ci in frontend/)"
fi

echo
echo "=== Summary ==="
echo "  PASS: $pass"
echo "  FAIL: $fail"
echo "  N/A:  $na"
if [[ "$fail" -eq 0 ]]; then
  echo "VERDICT: PASS (automated V1 UAT)"
  exit 0
fi
echo "VERDICT: FAIL"
exit 1
