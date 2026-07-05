#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/home/takatoshi/.Xauthority}"

case "$ACTION" in
  on)
    if command -v xset >/dev/null 2>&1; then
      xset dpms force on || true
    fi
    if command -v vcgencmd >/dev/null 2>&1; then
      vcgencmd display_power 1 >/dev/null || true
    fi
    ;;
  off)
    if command -v xset >/dev/null 2>&1; then
      xset dpms force off || true
    fi
    if command -v vcgencmd >/dev/null 2>&1; then
      vcgencmd display_power 0 >/dev/null || true
    fi
    ;;
  *)
    echo "Usage: $0 {on|off}" >&2
    exit 1
    ;;
esac
