#!/usr/bin/env bash
# System-wide prerequisites for Ink-style setup (/usr/bin/python3, no venv).
# Waveshare “old” epdconfig: spidev + RPi.GPIO. “New” tree may need gpiozero — use apt extras below.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-pip \
  python3-dev \
  gcc \
  spi-tools

echo "Installing Python deps system-wide (--break-system-packages is normal on PEP 668 Pi images) ..."
sudo python3 -m pip install --break-system-packages -r "$(dirname "$0")/../requirements.txt"

echo "Optional (new waveshare epdconfig with gpiozero on Bookworm):"
echo "  sudo apt-get install -y python3-gpiozero python3-lgpio"
echo "Then add Environment=GPIOZERO_PIN_FACTORY=lgpio to purin-dashboard.service if needed."
