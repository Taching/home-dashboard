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

output_enabled() {
  local target="$1"
  wlr-randr | awk -v target="$target" '
    $0 ~ "^" target " " { show=1 }
    show && /Enabled:/ { print $2; exit }
  '
}

preferred_mode() {
  local target="$1"
  wlr-randr | awk -v target="$target" '
    $0 ~ "^" target " " { show=1; next }
    show && /^[^ ]/ { exit }
    show && /\(preferred/ {
      res=$1
      hz=$3
      gsub(/,/,"",hz)
      if (res != "" && hz != "") {
        print res "@" hz
        exit
      }
    }
  '
}

OUTPUT="${DISPLAY_HDMI_OUTPUT:-}"
if [[ -z "$OUTPUT" ]]; then
  case "$ACTION" in
    off) OUTPUT="$(active_hdmi_output || first_hdmi_output || true)" ;;
    on|status) OUTPUT="$(first_hdmi_output || true)" ;;
  esac
fi

if [[ -z "$OUTPUT" ]]; then
  echo "No HDMI output found" >&2
  exit 1
fi

case "$ACTION" in
  on)
    mode="$(preferred_mode "$OUTPUT" || true)"
    if [[ -n "$mode" ]]; then
      wlr-randr --output "$OUTPUT" --on --mode "$mode"
    else
      wlr-randr --output "$OUTPUT" --on
    fi
    ;;
  off)
    # Idempotent: already-disabled outputs still count as success so the
    # scheduler can re-assert power-off without failing.
    if [[ "$(output_enabled "$OUTPUT" || true)" == "no" ]]; then
      exit 0
    fi
    wlr-randr --output "$OUTPUT" --off
    ;;
  status)
    output_enabled "$OUTPUT"
    ;;
  *)
    echo "Usage: $0 {on|off|status}" >&2
    exit 1
    ;;
esac
