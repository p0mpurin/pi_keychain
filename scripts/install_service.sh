#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_SRC="$ROOT/systemd/purin-dashboard.service"

if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "missing $SERVICE_SRC" >&2
  exit 1
fi

sudo cp "$SERVICE_SRC" /etc/systemd/system/purin-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable purin-dashboard.service
sudo systemctl restart purin-dashboard.service
sudo systemctl status purin-dashboard.service --no-pager
