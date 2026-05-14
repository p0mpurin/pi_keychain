# Purin Pi

Portable Raspberry Pi Zero 2 W + Waveshare e-paper control plane (Wi‑Fi AP + Flask dashboard).

Full task breakdown and acceptance criteria live in [`plan.md`](plan.md) at the repo root (development checkout may use another folder name — mirror it to `/home/purin/purin_pi` on device).

## First boot on the Pi

1. Clone this repo to `/home/purin/purin_pi` (adjust paths in `systemd/purin-dashboard.service` if you choose another location).
2. Ensure Waveshare sources exist at `/home/purin/e-Paper` **without modifying them**.
3. Confirm the panel module name matches `app/epd.py` → `PANEL_MODULE` (Task 1 in `plan.md`).
4. Install deps:

```bash
cd ~/purin_pi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For systemd we call system Python (`/usr/bin/python3 -m app.main`); install packages system-wide **or** change `ExecStart` to your venv interpreter.

5. Bring up the AP:

```bash
export PURIN_PSK='choose-a-strong-password'
chmod +x scripts/*.sh
./scripts/setup_ap.sh
```

6. Install captive DNS helper (NM shared dnsmasq):

```bash
./scripts/install_captive_dnsmasq.sh
```

7. Install and start the dashboard service:

```bash
./scripts/install_service.sh
```

8. Optional SD protection:

```bash
./scripts/enable_overlayroot.sh
sudo reboot
```

## Changing the Wi‑Fi password

```bash
export PURIN_PSK='new-secret'
./scripts/setup_ap.sh
```

The preset QR button reads `PURIN_PSK` (and `PURIN_AP_SSID`, default `purin-pi`) when rendering the Wi‑Fi QR payload.

## iOS captive portal caveat

The captive portal mini-browser does not behave like Safari (cookies/session quirks). If the sheet misbehaves, dismiss it and open Safari manually to `http://10.42.0.1`.

## Dashboard works but e‑ink never updates

The systemd unit runs as **`root`**, so Python’s **`Path.home()` is `/root`**, not `/home/purin`. The app must find Waveshare’s Python libs under **`…/e-Paper/RaspberryPi_JetsonNano/python/lib`**.

The shipped **`purin-dashboard.service`** sets **`PURIN_EPAPER_LIB=/home/purin/e-Paper/RaspberryPi_JetsonNano/python/lib`**. If your clone lives elsewhere, edit that path or set **`PURIN_EPAPER_HOME`** to the folder that contains **`RaspberryPi_JetsonNano/`**.

After changing the unit:

```bash
sudo systemctl daemon-reload
sudo systemctl restart purin-dashboard
journalctl -u purin-dashboard -n 30 --no-pager
```

You should see a line like **`waveshare_epd: added to sys.path -> …`**. If you see **`no library directory found`**, fix the path. Wrong panel driver: change **`PANEL_MODULE`** in **`app/epd.py`** to match your HAT (see Waveshare examples under **`python/examples/`**).

## Updating the app with overlayroot

When overlay root is enabled:

```bash
sudo overlayroot-chroot
cd /home/purin/purin_pi
git pull
pip install -r requirements.txt
exit
sudo reboot
```

## Local development off-device

Hardware drivers will fail without `/home/<you>/e-Paper`; set:

```bash
export PURIN_PORT=8765
export PURIN_ALLOWED_HOSTS=localhost,127.0.0.1
python -m app.main
```

Visit `http://127.0.0.1:8765`.

## Optional shutdown button

Install `gpiozero`, then run `scripts/shutdown_button.py` under systemd (sample unit not shipped — mirror `purin-dashboard.service`). Hold GPIO3 (default) for several seconds to trigger `systemctl poweroff`.
