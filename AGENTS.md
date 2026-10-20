# AGENTS.md

Repo: `github.com:Taching/home-dashboard.git` — a Raspberry Pi 5 kiosk dashboard
and "Daily OS" for one person (Toshi). Read [`docs/agent-handoff-chili.md`](docs/agent-handoff-chili.md)
before making product decisions.

## Verification

Run before committing:

```sh
make check   # Backend tests, frontend tests, lint, build
```

CI uses the same command. All checks must pass.

## Dry-run mode (default)

`CHILI_PRODUCTION_MODE` defaults to `false`. External side effects are blocked:

- Telegram / OpenClaw `notify_user`, `send`
- Notion writes (`complete`, `publish_progress`, training sync)
- Device control (BroadLink lights, SwitchBot pump, display power)
- LLM calls (OpenAI for calendar adjust, rerank, voice notification)

The Pi's production `.env` sets `CHILI_PRODUCTION_MODE=true`.

**Agents must NEVER enable production mode without explicit owner approval.**

## Red lines

1. **Never set `CHILI_PRODUCTION_MODE=true`** — real effects require owner approval.
2. **Never commit `.env`** or secrets. Never read `.env` in agent code.
3. **Never restyle the kiosk wall** — it's read-only, not a dashboard redesign surface.
4. **Never collapse the two TrainingService classes** — they coexist on purpose.
5. **Always run `make check`** before committing.
6. **Restart the kiosk after frontend changes** — see `.cursor/rules/restart-kiosk-after-frontend.mdc`.

## Layout

- `backend/` — FastAPI (Python 3.12, SQLAlchemy + SQLite). Domain: `app/domain/*`, routes: `app/api/*`.
- `frontend/` — React 19 + TypeScript + Vite kiosk UI (`src/`), phone pages (`src/pages/`).
- `deploy/` — systemd units, shell scripts for Compose, kiosk, watchdog.
- `openclaw-skills/` — skills for the OpenClaw agent (daily-os, bjj-training, lights, display).
- `docs/` — `agent-handoff-chili.md` is canonical; others are historical.
- `data/` — SQLite DB, learned IR codes. Gitignored, never commit.

## Running

```sh
./start.sh                 # Full stack, auto-detects Pi
./start.sh --no-calendar   # Dev machine
```

Dashboard binds `127.0.0.1:8080`. Stop with `docker compose down`.

## Tests

Backend (stdlib unittest):
```sh
cd backend && python -m unittest discover -s tests -v
```

Frontend:
```sh
cd frontend && npm test    # Unit tests
cd frontend && npm run lint
cd frontend && npm run build  # Typecheck + bundle
```

## Key conventions

- **Daily Plan is the single read model.** Don't invent a parallel store.
- **Secrets stay backend-only.** Never send tokens to the browser.
- **Never expose to public internet.** Remote access is Tailscale only.
- **LLM calls are bounded**: on-demand coach, once-daily, once-weekly. No automatic per-request calls.

See `docs/agent-handoff-chili.md` for full product context and `docs/agent-handoff-efficiency.md` for architecture cuts.
