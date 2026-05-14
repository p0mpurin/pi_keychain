#!/usr/bin/env bash
# Enable tmpfs overlay root (requires reboot). Review package availability on your image first.
set -euo pipefail

if ! command -v overlayroot-chroot >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y overlayroot
fi

sudo tee /etc/overlayroot.conf >/dev/null <<'EOF'
overlayroot="tmpfs"
EOF

echo "overlayroot configured. Reboot to activate."
echo "To perform updates later: sudo overlayroot-chroot"
