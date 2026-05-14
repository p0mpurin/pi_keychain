#!/usr/bin/env bash
# Prerequisites for pip install -r requirements.txt when building PyPI package "lgpio"
# on Raspberry Pi OS (SWIG wraps liblgpio; without swig, pip fails with: command 'swig' failed).
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  swig \
  python3-dev \
  python3-venv \
  gcc \
  liblgpio-dev

echo "Done. Next: cd to project, source .venv/bin/activate, pip install -r requirements.txt"
