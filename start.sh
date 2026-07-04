#!/usr/bin/env bash
# Start the Chili Home Dashboard with the correct Compose configuration.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$root_dir"

use_voice=true
use_calendar=true
detach=true
build=true

usage() {
  cat <<'EOF'
Usage: ./start.sh [options]

Starts the complete dashboard stack: dashboard, voice worker, and Apple
Calendar bridge. On a Raspberry Pi it automatically enables the hardware
Compose override.

Options:
  --no-voice    Do not start the voice worker.
  --no-calendar Do not start the Apple Calendar bridge.
  --foreground  Stream container logs instead of running in the background.
  --no-build    Do not rebuild container images before starting.
  -h, --help    Show this help.
EOF
}

for argument in "$@"; do
  case "$argument" in
    --no-voice) use_voice=false ;;
    --no-calendar) use_calendar=false ;;
    --foreground) detach=false ;;
    --no-build) build=false ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'Unknown option: %s\n\n' "$argument" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f .env ]]; then
  printf 'Missing .env. Create it with: cp .env.example .env\n' >&2
  exit 1
fi

compose_files=(-f compose.yaml)
if [[ -r /proc/device-tree/model ]] && grep -q 'Raspberry Pi' /proc/device-tree/model; then
  compose_files+=(-f compose.pi.yaml)
fi
if "$use_calendar"; then
  compose_files+=(-f compose.apple-calendar-bridge.yaml)
fi

compose_options=()
if "$use_voice"; then
  compose_options+=(--profile voice)
fi

compose_args=(up)
if "$detach"; then
  compose_args+=(-d)
fi
if "$build"; then
  compose_args+=(--build)
fi

exec docker compose "${compose_files[@]}" "${compose_options[@]}" "${compose_args[@]}"
