# AGENTS.md

Repo: `github.com:Taching/home-dashboard.git` — a Raspberry Pi 5 kiosk dashboard
and "Daily OS" for one person (Toshi). Not a generic fitness/smart-home demo —
see [`docs/agent-handoff-chili.md`](docs/agent-handoff-chili.md) before making
product decisions. That file has the full product context (who Toshi is, what
he explicitly does not want, the Daily Plan model, the training policy). Read
it first if you're touching planning, training, notifications, or the wall UI.

## Layout

- `backend/` — FastAPI control API (Python 3.12, SQLAlchemy + SQLite, APScheduler-style jobs in `app/jobs/`). Domain logic lives in `backend/app/domain/*`, HTTP routes in `backend/app/api/*`.
- `frontend/` — React 19 + TypeScript + Vite kiosk UI (`frontend/src`), plus the phone/daily pages under `frontend/src/pages`.
- `walkingpad-collector/` — BLE collector for the KingSmith WalkingPad S1, host networking, own container.
- `macos/apple-calendar-bridge/` — Swift/macOS helper that syncs Apple Calendar to the Pi over a read-only bridge.
- `deploy/` — systemd units + shell scripts for Compose lifecycle, Chromium kiosk, health watchdog, and OpenClaw automation hooks (`openclaw-*.sh`).
- `openclaw-skills/` — skills the OpenClaw agent uses to call this dashboard's automation API (daily-os, bjj-training, lights, display).
- `docs/` — product/architecture handoffs and design notes. `docs/agent-handoff-chili.md` is the canonical one; treat others (`agent-handoff-efficiency.md`, `plan.md`, `design.md`) as historical/point-in-time unless corroborated by current code.
- `data/` — SQLite DB (`chili.db`) and learned IR codes. Never commit; gitignored.
- `.env` / `.env.example` — all integration config (weather, BroadLink, Notion, Spotify, OpenClaw, SwitchBot, WalkingPad). Copy `.env.example`, fill only what the active phase needs.

## Running it

- `./start.sh` — the normal entry point. Auto-detects Raspberry Pi hardware and includes the right Compose override. Flags: `--no-calendar`, `--foreground`, `--help`.
- Plain dev machine: `./start.sh --no-calendar`.
- On the Pi directly: `docker compose -f compose.yaml -f compose.pi.yaml up --build -d`.
- Optional profile: `--profile walkingpad` (see README for env vars it needs).
- Dashboard binds `127.0.0.1:8080`. Stop with `docker compose down` (add `-f compose.pi.yaml` on the Pi).

## Tests

- Backend: stdlib `unittest`, not pytest (pytest isn't installed in `backend/.venv`).
  ```sh
  cd backend && .venv/bin/python -m unittest discover -s tests
  ```
  A handful of tests fail/error without a properly configured local `.env`/data dir (e.g. sqlite path, settings) — check whether a failure is pre-existing/environmental before assuming your change broke it.
- Frontend: `cd frontend && npm test` (runs `tsx --test src/lib/*.test.ts` — only `lib/` has unit tests today). Lint with `npm run lint`, build/typecheck with `npm run build` (`tsc -b && vite build`).

## Coach, free-text replanning, preferences, sleep, weekly review

Added on top of the base planner/adjuster — all backend pieces live in
`backend/app/domain/training/review.py`, `training/adjust.py`,
`training_preferences.py`, `weekly.py`, and routes in `api/training.py` /
`api/daily.py`. Frontend pages are phone-only (never the kiosk wall), reusing
the `is-workout` styling from `workout.css`.

- **On-demand coach** — `POST /training/sessions/{id}/coach`. Requires the
  session to already have a logged result. Builds a prompt via
  `workout_review_prompt()`, calls `openclaw_service.send()` once, falls back
  to the deterministic `local_workout_review()`. Never automatic — triggered
  only by the "Ask coach" button (`components/AskCoachButton.tsx`) on the
  workout page and the daily page once a session is logged.
- **Free-text replan** — `POST /training/replan` (phone-facing, unauthenticated;
  distinct from the bearer-token `/automation/training/adjust`). Thin wrapper
  around the existing `CalendarAdjuster.adjust()` — same fast-path/GPT
  interpret → `reconcile()` pipeline everything else uses. Catches
  `ValueError`/`KeyError` into clean 400/404s instead of a 500. UI:
  `pages/ScheduleChangePage.tsx` (`/schedule-change`), optimistic submit
  (button says "Sending…" immediately, then reconciles with the real
  How/Why decision or error), plus a read-only "This week" list so Toshi
  can see the schedule while describing what changed.
- **Training preferences** — `GET`/`PUT /training/preferences`, a single
  free-text notes field (`TrainingPreferencesService`, singleton row). Fed
  into the coach and replan prompts via `.prompt_snippet()` for flavor only.
  **Never wire this into `CalendarAdjuster._apply`, `policy.py`,
  `constraints.py`, `ranker.py`, or `scheduler.py`** — it must not gate the
  deterministic scheduler. UI: `pages/TrainingPreferencesPage.tsx`
  (`/training/preferences`).
- **Sleep logging** — `POST /daily/{day}/sleep`, one optional field
  (`DailyWellbeingCheckIn.sleep_hours`, columns already existed, unused
  before this). Deliberately **not** a readiness form (Toshi explicitly does
  not want sleep/fatigue/soreness/motivation as a required morning
  check-in, see `docs/agent-handoff-chili.md`) — it never gates closing the
  day and stays editable. UI: `SleepForm` in `components/DailyBriefingPage.tsx`.
- **Weekly LLM training review** — tied to the existing Sunday check-in
  (`daily_sunday()` in `api/daily.py`), not a separate surface. On submit,
  pulls `training.week_review(week_start)` (planned vs completed by
  discipline, RPE trend, recovery flags) plus the weight delta and
  preferences, calls `openclaw_service.send()` once via
  `weekly_training_review_prompt()`, falls back to
  `local_weekly_training_review()`. Stored on `WeeklyReview.coach_review`
  (new column — added via `_ensure_column` in `database/session.py`, no
  Alembic) and surfaced both in the Telegram notify and inline on the
  Sunday "done" card. This replaced the old `WeeklyService.review_prompt()`,
  which built a similar prompt but was never actually wired to any LLM call
  — don't resurrect it as a second parallel path.
- **Icons** — `components/icons.tsx` (inline SVG, `currentColor`, no icon
  library dependency). Reuse these rather than inlining new `<svg>` blocks
  in page components.
- **LLM call budget stays intentionally bounded**: on-demand (coach), once a
  day (`close_day_prompt`, only after every required daily answer is in),
  once a week (Sunday review). This mirrors the Sep-13 efficiency cut that
  removed per-workout-log agent turns for cost/latency — don't add a new
  automatic-per-log or automatic-per-page-load LLM call without a similar
  bounded trigger.

## Conventions and red lines

- **Restart the kiosk after any frontend deploy.** Chromium caches the old hashed JS/CSS bundle. After rebuilding the `frontend` container: check `systemctl is-active chili-kiosk.service`, then `sudo systemctl restart chili-kiosk.service`, and confirm it's `active`. Do not restart the kiosk for backend-only changes. (See `.cursor/rules/restart-kiosk-after-frontend.mdc`.)
- **Don't restyle the kiosk or add features speculatively.** Prior handoffs are explicit: keep the wall a read-only glance driven by the Daily Plan, not a second Notion or a four-widget dashboard. If a change looks like a redesign or a new surface, confirm with Toshi first.
- **Daily Plan is the single read model.** `GET /api/v1/daily/{day}` and `GET /api/v1/plan/{day}` both return `DailyPlanService.build()`'s object; meetings/tasks/training/home-reminders stay sourced from Apple Calendar, Notion, `TrainingSession`, and the reminder jobs respectively — don't invent a parallel store.
- **Two training stacks currently coexist on purpose**: `app.domain.training.TrainingService` (planner, source of truth for the Daily Plan) and `app.domain.training_logs.TrainingService` (legacy log, still read by `/workout`). Don't collapse them without checking `docs/agent-handoff-chili.md` / `agent-handoff-efficiency.md` for why they're still split.
- **Secrets stay backend-only.** OpenClaw gateway token, Notion token, Spotify OAuth secrets, `DASHBOARD_AUTOMATION_TOKEN`, etc. are read by the backend and never sent to the browser.
- **Never expose the dashboard to the public internet.** Remote access is Tailscale Serve only (see `docs/tailscale-remote-access.md`).
- **`data/` and learned IR codes are gitignored** — don't commit `data/chili.db` or `data/learned-codes/*`.
