#!/usr/bin/env bash
# Configure private HTTPS access to the dashboard through Tailscale Serve.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_source="$root_dir/deploy/chili-tailscale-serve.service"
unit_destination=/etc/systemd/system/chili-tailscale-serve.service

if ! command -v tailscale >/dev/null 2>&1; then
  printf '%s\n' 'Tailscale is not installed.' \
    'Install it first using the official Linux instructions:' \
    'https://tailscale.com/docs/install/linux'
  exit 1
fi

if ! sudo tailscale ip -4 >/dev/null; then
  printf '%s\n' 'Sign this Pi into your Tailscale account first:' \
    '  sudo tailscale up' \
    'Then rerun this script.'
  exit 1
fi

printf '%s\n' 'Installing the Tailscale Serve systemd unit...'
sudo install -m 0644 "$unit_source" "$unit_destination"
sudo systemctl daemon-reload
sudo systemctl enable --now chili-tailscale-serve.service

printf '%s\n' \
  'Private dashboard access is configured.' \
  'Run: tailscale serve status' \
  'Open the displayed HTTPS URL from a phone signed into the same Tailscale account.'
