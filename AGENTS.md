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

## Conventions and red lines

- **Restart the kiosk after any frontend deploy.** Chromium caches the old hashed JS/CSS bundle. After rebuilding the `frontend` container: check `systemctl is-active chili-kiosk.service`, then `sudo systemctl restart chili-kiosk.service`, and confirm it's `active`. Do not restart the kiosk for backend-only changes. (See `.cursor/rules/restart-kiosk-after-frontend.mdc`.)
- **Don't restyle the kiosk or add features speculatively.** Prior handoffs are explicit: keep the wall a read-only glance driven by the Daily Plan, not a second Notion or a four-widget dashboard. If a change looks like a redesign or a new surface, confirm with Toshi first.
- **Daily Plan is the single read model.** `GET /api/v1/daily/{day}` and `GET /api/v1/plan/{day}` both return `DailyPlanService.build()`'s object; meetings/tasks/training/home-reminders stay sourced from Apple Calendar, Notion, `TrainingSession`, and the reminder jobs respectively — don't invent a parallel store.
- **Two training stacks currently coexist on purpose**: `app.domain.training.TrainingService` (planner, source of truth for the Daily Plan) and `app.domain.training_logs.TrainingService` (legacy log, still read by `/workout`). Don't collapse them without checking `docs/agent-handoff-chili.md` / `agent-handoff-efficiency.md` for why they're still split.
- **Secrets stay backend-only.** OpenClaw gateway token, Notion token, Spotify OAuth secrets, `DASHBOARD_AUTOMATION_TOKEN`, etc. are read by the backend and never sent to the browser.
- **Never expose the dashboard to the public internet.** Remote access is Tailscale Serve only (see `docs/tailscale-remote-access.md`).
- **`data/` and learned IR codes are gitignored** — don't commit `data/chili.db` or `data/learned-codes/*`.
