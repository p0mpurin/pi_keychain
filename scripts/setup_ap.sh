#!/usr/bin/env bash
# NetworkManager Wi-Fi AP for Purin Pi (idempotent).
set -euo pipefail

SSID="${PURIN_AP_SSID:-purin-pi}"
PSK="${PURIN_PSK:-changeme-please}"
CON="${PURIN_NM_CONNECTION:-purin-ap}"

if nmcli -t -f NAME connection show | grep -Fxq "$CON"; then
  nmcli connection delete "$CON"
fi

nmcli connection add type wifi ifname wlan0 con-name "$CON" autoconnect yes ssid "$SSID"
nmcli connection modify "$CON" 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared
nmcli connection modify "$CON" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK"
nmcli connection up "$CON"

echo "wlan0 IPv4:"
nmcli -g IP4.ADDRESS device show wlan0 || true
