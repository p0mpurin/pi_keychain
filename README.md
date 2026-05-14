# Purin Pi

Portable Raspberry Pi Zero 2 W + Waveshare e-paper control plane (Wi‑Fi AP + Flask dashboard).

Full task breakdown and acceptance criteria live in [`plan.md`](plan.md) at the repo root. The sample unit assumes `/home/purin/pi_keychain` — edit **`WorkingDirectory`**, **`PYTHONPATH`**, and **`PURIN_EPAPER_LIB`** if you install elsewhere (compare with a **known‑working** `systemctl cat` for your “ink” service).

## First boot on the Pi

1. Clone this repo to `/home/purin/pi_keychain` (or your path; keep unit paths in sync).
2. Ensure Waveshare sources exist at `/home/purin/e-Paper` **without modifying them**.
3. Confirm the panel module name matches `app/epd.py` → `PANEL_MODULE` (Task 1 in `plan.md`).
4. Enable **SPI** (Raspberry Pi OS: **Raspberry Pi Configuration** → Interfaces → SPI, or `raspi-config`), then reboot if needed.
5. **Ink-style stack — system Python, no venv** (same interpreter as **`ExecStart=/usr/bin/python3`** in `systemd/purin-dashboard.service`):

```bash
cd ~/pi_keychain
chmod +x scripts/install_pi_deps.sh
./scripts/install_pi_deps.sh
```

That installs **`requirements.txt`** with **`sudo python3 -m pip install --break-system-packages …`** (normal on PEP‑668 Pi images).

**Two possible Waveshare trees:** open **`…/python/lib/waveshare_epd/epdconfig.py`** → **`class RaspberryPi` → `__init__`** on your Pi. **Older** ink-style trees often use **`spidev` + `RPi.GPIO`** only (what `requirements.txt` targets). **Current** upstream [epdconfig.py](https://github.com/waveshareteam/e-Paper/blob/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epdconfig.py) uses **`gpiozero`** (not **`RPi.GPIO`**) for pins. If imports fail after step 5:

```bash
sudo apt-get install -y python3-gpiozero python3-lgpio
# Optionally uncomment in the unit:
# Environment=GPIOZERO_PIN_FACTORY=lgpio
```

If you prefer **PyPI `lgpio`** instead of **`apt python3-lgpio`**, install build deps first: **`sudo apt-get install -y swig python3-dev gcc liblgpio-dev`**, then **`sudo python3 -m pip install --break-system-packages lgpio`**.

**Optional venv** (only if you insist on isolating packages): create **`.venv`**, change **`ExecStart`** to that interpreter, and **`pip install -r requirements.txt`** there — but then match **the same** Waveshare **`PYTHONPATH`** / env as your working setup.

Quick check (same as **`ExecStart`** — adjust paths):

```bash
/usr/bin/python3 -c "import spidev; print('spidev OK')"
/usr/bin/python3 -c "import RPi.GPIO; print('RPi.GPIO OK')" 2>/dev/null || echo 'no RPi.GPIO (maybe gpiozero tree)'
PYTHONPATH=/home/purin/pi_keychain:/home/purin/e-Paper/RaspberryPi_JetsonNano/python/lib \
  /usr/bin/python3 -c "import waveshare_epd.epd2in13_V4; print('waveshare OK')"
```

6. Bring up the AP:

```bash
export PURIN_PSK='choose-a-strong-password'
chmod +x scripts/*.sh
./scripts/setup_ap.sh
```

7. Install captive DNS helper (NM shared dnsmasq):

```bash
./scripts/install_captive_dnsmasq.sh
```

8. Install and start the dashboard service:

```bash
./scripts/install_service.sh
```

9. Optional SD protection:

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

You should see a line like **`waveshare_epd: added to sys.path → …`**. If you see **`no library directory found`**, fix the path. Wrong panel driver: change **`PANEL_MODULE`** in **`app/epd.py`** to match your HAT (see Waveshare examples under **`python/examples/`**).

### E‑paper orientation / inverted black & white

Adjust from the **dashboard** (Text page, first card): **rotation** and **invert**. That writes **`data/display_settings.json`**; on every start the app loads that file first and only falls back to **`PURIN_EPD_ROTATE`** / **`PURIN_EPD_INVERT`** in the unit if the file is absent or invalid.

- **API:** **`GET /api/display_settings`**, **`POST /api/display_settings`** with JSON **`{"rotate": 90, "invert": true}`** (optional **`invert`** in JSON keeps current value if omitted).
- Remove the JSON file to revert to env-only behaviour.
- **Upside‑down landscape:** **`90` → `270`** in the form.
- **`/api/status`** includes **`display.rotate`** and **`display.invert`**.

### Log noise: werkzeug vs e‑paper

`/api/clear` and other routes show **`POST … werkzeug`** lines at **INFO**; that proves the browser talked to Flask, **not** that SPI ran. Startup also logs **`waveshare_epd: added …`**.

With current code **`werkzeug` is turned down unless** you set **`PURIN_LOG_HTTP=1`**, so **`journalctl -u purin-dashboard -f`** should show **`app.epd`** lines after each refresh, e.g. **`EPD clear complete`** and **`EPD pushed frame`** (buffer bytes, dimensions).

- Debug everything: **`Environment=PURIN_LOG_LEVEL=DEBUG`** under **`[Service]`**
- Restore per-request **`POST /…`** logs: **`Environment=PURIN_LOG_HTTP=1`**

Follow live logs:

```bash
sudo journalctl -u purin-dashboard -f
```

**Hang with no `EPD … returned OK`:** if the last line is **`EPD: calling driver init()`** or **`EPD clear: calling init()`** and nothing after, the stock driver is blocked in **`ReadBusy()`** (BUSY pin / GPIO / SPI — not Flask). Confirm with Waveshare’s own script:  
`python3 ~/e-Paper/RaspberryPi_JetsonNano/python/examples/epd_2in13_V4_test.py`.

If the last line is **`EPD clear: mutex acquired`** and nothing after (older builds), that was a **`threading.Lock` re-entrancy bug** in **`clear()`** (now fixed with **`RLock`**).

### Match a legacy app or save power between frames

By default we **avoid `epd.sleep()` after each draw**, matching **`epd_2in13_V4_test.py`** (sleep ends with **`module_exit()`**, which makes the controller look “asleep until the second refresh” on some setups).

Enable low-power teardown after **every successful draw** only if you need it:

```bash
Environment=PURIN_EPD_SLEEP_AFTER_DRAW=1
```

Optional Waveshare-style pauses after **`init` / `Clear`** on first use (seconds, **`0`** = off):

```bash
Environment=PURIN_EPD_INIT_SLEEP_SEC=1
```

## Updating the app with overlayroot

When overlay root is enabled:

```bash
sudo overlayroot-chroot
cd /home/purin/pi_keychain
git pull
./scripts/install_pi_deps.sh   # or: sudo python3 -m pip install --break-system-packages -r requirements.txt
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
