#!/usr/bin/env bash
set -euo pipefail

# Read the dashboard's structured health explanation for OpenClaw or a host tool.
BASE_URL="${CHILI_DASHBOARD_URL:-http://127.0.0.1:8080}"
curl -fsS "${BASE_URL}/api/v1/health/details"
echo
