# Chili Home Dashboard — unified verification command.
# Run `make check` before committing. CI uses the same command.

.PHONY: check test-backend test-frontend lint build test-pr-stack pr-stack uat-v1 help

# Default: run all checks
check: test-backend test-frontend lint build test-pr-stack
	@echo ""
	@echo "✓ All checks passed"

test-pr-stack:
	@echo "→ PR stack script"
	@scripts/tests/test_create_pr_stack.sh

# Backend: stdlib unittest (not pytest)
# Set env vars so tests work without a configured .env/data dir (mirrors CI).
test-backend:
	@echo "→ Backend tests"
	DATABASE_URL="sqlite://" SENSOR_ENABLED=false TZ=Asia/Tokyo CHILI_PRODUCTION_MODE=false \
		python3 -m unittest discover -s backend/tests -v

# Frontend: tsx --test for lib/*.test.ts
test-frontend:
	@echo "→ Frontend tests"
	cd frontend && npm test

# Frontend lint (eslint)
lint:
	@echo "→ Frontend lint"
	cd frontend && npm run lint

# Frontend build (tsc + vite build)
build:
	@echo "→ Frontend build"
	cd frontend && npm run build

# Create an open (non-draft) PR stack. Pass STEPS='b1|title|body' STEPS+=... via
# the script directly; this target only prints usage.
pr-stack:
	@scripts/create-pr-stack.sh --help

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  check         Run all verification (default)"
	@echo "  test-backend  Run backend unittests"
	@echo "  test-frontend Run frontend tests"
	@echo "  lint          Run frontend linter"
	@echo "  build         Build frontend (typecheck + bundle)"
	@echo "  test-pr-stack Offline smoke test for create-pr-stack.sh"
	@echo "  pr-stack      Show create-pr-stack.sh usage (open stacked PRs)"
	@echo "  uat-v1        Automated UAT for workout library V1 (M1–M4)"
	@echo "  help          Show this help"

uat-v1:
	@scripts/verify_uat_v1.sh
