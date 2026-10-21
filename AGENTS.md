# AGENTS.md

Repo: `github.com:Taching/home-dashboard.git` — a Raspberry Pi 5 kiosk dashboard
and "Daily OS" for one person (Toshi). Read [`docs/agent-handoff-chili.md`](docs/agent-handoff-chili.md)
before making product decisions.

## Verification

Run before committing:

```sh
make check        # Priority gate: core backend + frontend + lint + build
make regression   # Full suite (priority + backend/tests_regression)
```

CI uses `make check`. All priority checks must pass before merge.
Use `make regression` when touching peripherals (library, WalkingPad, Notion sync, rain, backfill) or before a big release.

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
5. **Always run `make check`** before committing. Use `make regression` for the full backend suite.
6. **Restart the kiosk after frontend changes** — see `.cursor/rules/restart-kiosk-after-frontend.mdc`.
7. **Never open draft PRs** — create them ready for review. Multi-step work must be one stacked set (see below).

## Pull requests / stacks

- **Single change** → one ready PR to `master` (`gh pr create`, no `--draft`).
- **Ordered milestones** → one linear branch stack, then create **all** PRs in one go with `scripts/create-pr-stack.sh`.
  - Branch N contains Branch N-1's tip.
  - PR 1 bases on `master`; PR N bases on Branch N-1.
  - Do not open duplicate PRs that each target `master` with overlapping commits.
- **Merge bottom-up.** After merging a lower PR, delete its head (preferred) or `gh pr edit <next> --base master` before merging the tip — otherwise the tip merges into a dead feature branch and never lands on `master`.

```sh
# After all stack branches are pushed:
scripts/create-pr-stack.sh --base master \
  --step 'cursor/m2|feat: M2 logging|## Summary'$'\n''- trustworthy logging' \
  --step 'cursor/m3|feat: M3 analyzer|## Summary'$'\n''- weekly review'
```

See `.cursor/rules/pr-stack.mdc`.

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

- **Keep `docs/what-chili-does.md` in sync with every commit.** It is Toshi's plain-language overview of what the dashboard does. Before committing any change that adds, removes, or changes user-visible behavior (a wall or phone surface, a Telegram message or its timing, training templates/progression/deload, cut targets, integrations, schedules), update the affected section in the same commit and bump the `_Last updated_` date. Pure refactors, test-only, and internal fixes with no visible effect don't need it. If unsure, check the doc against the change and say in the commit message that it was reviewed. (See `.cursor/rules/update-what-chili-does.mdc`.)
- **Daily Plan is the single read model.** Don't invent a parallel store.
- **Secrets stay backend-only.** Never send tokens to the browser.
- **Never expose to public internet.** Remote access is Tailscale only.
- **LLM calls are bounded**: on-demand coach, once-daily, once-weekly. No automatic per-request calls.
- **`data/` and learned IR codes are gitignored** — don't commit `data/chili.db` or `data/learned-codes/*`.

See `docs/agent-handoff-chili.md` for full product context and `docs/agent-handoff-efficiency.md` for architecture cuts.
