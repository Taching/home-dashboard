# Claude Code Instructions

This file defers to AGENTS.md, which is the canonical agent documentation.

Read AGENTS.md first, then docs/agent-handoff-chili.md for full product context.

## Quick start

```bash
make check    # Run all verification (tests, lint, build)
```

## Dry-run mode

By default, CHILI_PRODUCTION_MODE=false. External side effects (Telegram,
Notion writes, device control, LLM calls) are blocked and logged.

**Never enable production mode without explicit owner approval in the chat.**

## Red lines

- Never set CHILI_PRODUCTION_MODE=true
- Never commit .env or secrets
- Never restyle the kiosk wall
- Never collapse the two TrainingService classes
- Always run `make check` before committing
- Keep `docs/what-chili-does.md` in sync with visible behavior changes
- Never open draft PRs; multi-step work → `scripts/create-pr-stack.sh` (open stacked set)
