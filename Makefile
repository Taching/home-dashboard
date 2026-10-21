# Chili Home Dashboard — verification commands.
# `make check` = commit/CI gate (priority). `make regression` = full suite.

.PHONY: check regression test-backend test-backend-regression test-frontend lint build test-pr-stack pr-stack uat-v1 help

# Prefer the backend venv (Pi/local dev); CI has none and uses its own python3.
PYTHON ?= $(if $(wildcard backend/.venv/bin/python),backend/.venv/bin/python,python3)

# CHILI_ENV_FILE= keeps the Pi's production .env (flag + API keys) out of tests.
BACKEND_ENV = CHILI_ENV_FILE= DATABASE_URL="sqlite://" SENSOR_ENABLED=false TZ=Asia/Tokyo CHILI_PRODUCTION_MODE=false PYTHONPATH=backend

# Default: priority verification (what CI runs)
check: test-backend test-frontend lint build test-pr-stack
	@echo ""
	@echo "✓ Priority checks passed (make regression for the full suite)"

# Full regression: priority backend + regression backend + frontend + lint + build
regression: test-backend test-backend-regression test-frontend lint build test-pr-stack
	@echo ""
	@echo "✓ Full regression passed"

test-pr-stack:
	@echo "→ PR stack script"
	@scripts/tests/test_create_pr_stack.sh

# Priority backend suites (backend/tests/) — dry-run, daily, training core, notify, cut
test-backend:
	@echo "→ Backend tests (priority)"
	$(BACKEND_ENV) $(PYTHON) -m unittest discover -s backend/tests -v

# Broader / peripheral suites (backend/tests_regression/)
test-backend-regression:
	@echo "→ Backend tests (regression)"
	$(BACKEND_ENV) $(PYTHON) -m unittest discover -s backend/tests_regression -v

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
	@echo "  check                   Priority verification (default, CI gate)"
	@echo "  regression              Full suite: priority + regression backend"
	@echo "  test-backend            Priority backend unittests"
	@echo "  test-backend-regression Regression backend unittests"
	@echo "  test-frontend           Frontend tests"
	@echo "  lint                    Frontend linter"
	@echo "  build                   Frontend typecheck + bundle"
	@echo "  test-pr-stack           Offline smoke test for create-pr-stack.sh"
	@echo "  pr-stack                Show create-pr-stack.sh usage"
	@echo "  uat-v1                  Automated UAT for workout library V1"
	@echo "  help                    Show this help"

uat-v1:
	@scripts/verify_uat_v1.sh
