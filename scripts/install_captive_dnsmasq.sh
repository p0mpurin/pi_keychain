#!/usr/bin/env bash
# Redirect all DNS queries from NM shared hotspots to the Pi (captive portal helper).
set -euo pipefail

CONF_DIR="/etc/NetworkManager/dnsmasq-shared.d"
CONF_FILE="$CONF_DIR/captive.conf"

sudo mkdir -p "$CONF_DIR"
echo 'address=/#/10.42.0.1' | sudo tee "$CONF_FILE" >/dev/null
echo "Wrote $CONF_FILE — reload NetworkManager to apply."

if sudo systemctl reload NetworkManager 2>/dev/null; then
  echo "NetworkManager reloaded."
else
  echo "Could not reload NetworkManager automatically; reboot or run: sudo nmcli general reload"
fi
