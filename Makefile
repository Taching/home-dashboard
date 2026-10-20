# Chili Home Dashboard — unified verification command.
# Run `make check` before committing. CI uses the same command.

.PHONY: check test-backend test-frontend lint build help

# Default: run all checks
check: test-backend test-frontend lint build
	@echo ""
	@echo "✓ All checks passed"

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

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  check         Run all verification (default)"
	@echo "  test-backend  Run backend unittests"
	@echo "  test-frontend Run frontend tests"
	@echo "  lint          Run frontend linter"
	@echo "  build         Build frontend (typecheck + bundle)"
	@echo "  help          Show this help"
