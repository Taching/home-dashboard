#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

sudo install -m 0644 "$root_dir/deploy/chili-health-watchdog.service" /etc/systemd/system/chili-health-watchdog.service
sudo install -m 0644 "$root_dir/deploy/chili-health-watchdog.timer" /etc/systemd/system/chili-health-watchdog.timer
sudo systemctl daemon-reload
sudo systemctl enable --now chili-health-watchdog.timer

echo "Chili health watchdog installed and running every five minutes."
