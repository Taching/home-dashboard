#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/1000}"

if ! command -v wlr-randr >/dev/null 2>&1; then
  echo "wlr-randr is not installed" >&2
  exit 1
fi

if [[ ! -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ]]; then
  echo "Wayland socket unavailable at ${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" >&2
  exit 1
fi

first_hdmi_output() {
  wlr-randr | awk '/^HDMI-A-/{print $1; exit}'
}

active_hdmi_output() {
  wlr-randr | awk '
    /^HDMI-A-/{name=$1}
    /Enabled: yes/ { if (name != "") { print name; exit } }
  '
}

OUTPUT="${DISPLAY_HDMI_OUTPUT:-}"
if [[ -z "$OUTPUT" ]]; then
  case "$ACTION" in
    off) OUTPUT="$(active_hdmi_output || true)" ;;
    on) OUTPUT="$(first_hdmi_output || true)" ;;
    status) OUTPUT="$(active_hdmi_output || first_hdmi_output || true)" ;;
  esac
fi

if [[ -z "$OUTPUT" ]]; then
  echo "No HDMI output found" >&2
  exit 1
fi

case "$ACTION" in
  on)
    wlr-randr --output "$OUTPUT" --on
    ;;
  off)
    wlr-randr --output "$OUTPUT" --off
    ;;
  status)
    wlr-randr | awk -v target="$OUTPUT" '
      $0 ~ "^" target " " { show=1 }
      show && /Enabled:/ { print $2; exit }
    '
    ;;
  *)
    echo "Usage: $0 {on|off|status}" >&2
    exit 1
    ;;
esac
