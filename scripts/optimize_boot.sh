#!/usr/bin/env bash
# Boot optimizations — each block is optional; comment out what you still need.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT="$ROOT/scripts/boot_report.txt"

{
  echo "=== systemd-analyze (before tweaks snapshot) $(date -Is) ==="
  systemd-analyze || true
  echo
  systemd-analyze blame | head -n 25 || true
} >"$REPORT"

echo "Baseline recorded at $REPORT"

# Bluetooth serial helper — disable if you do not use Bluetooth.
sudo systemctl disable --now hciuart.service 2>/dev/null || true
sudo systemctl disable --now bluetooth.service 2>/dev/null || true

sudo systemctl disable --now triggerhappy.service 2>/dev/null || true
sudo systemctl disable --now ModemManager.service 2>/dev/null || true

echo "Consider adding dtoverlay=disable-bt to /boot/firmware/config.txt manually if UART conflicts appear."
echo "HDMI can be disabled via raspi-config nonint do_audio 2 or vcdbg tools on legacy stacks."

{
  echo
  echo "=== systemd-analyze (after tweaks) $(date -Is) ==="
  systemd-analyze || true
} >>"$REPORT"
