# Purin Pi — E-Ink Keychain Dashboard

> Build spec for an AI coding assistant (Cursor). Implement tasks in order. Each task has a goal, deliverable files, and acceptance criteria. Do **not** skip ahead — earlier tasks de-risk later ones.

---

## 0. Project context

**Hardware**
- Raspberry Pi Zero 2 W (aarch64)
- Waveshare e-ink HAT (model TBD — confirm in Task 1; assume `epd2in13_V4` until told otherwise)
- Powered via USB from a phone (Android primary, iOS best-effort)

**OS / environment**
- Debian 13 (trixie), kernel 6.12, NetworkManager is the default network stack
- Python 3 available system-wide
- User: `purin`, home: `/home/purin`
- Existing repo at `~/e-Paper` (Waveshare drivers) — do not modify it; import from it
- Project root: `~/purin_pi`

**Goal**
Plug Pi into phone → Pi boots → Pi hosts Wi-Fi AP → phone connects → captive portal opens a web dashboard → user can push content to the e-ink screen (text, drawings, QR codes, notes, etc.).

**Non-goals (for v1)**
- USB gadget/RNDIS networking (Wi-Fi AP only)
- Internet passthrough from phone to Pi
- Multi-user auth (single-user device)

---

## 1. Architecture

```
┌─────────┐  USB power   ┌──────────────────────────────┐
│  Phone  │ ───────────► │  Pi Zero 2 W                 │
│         │              │                              │
│         │  Wi-Fi       │  wlan0 (AP, 10.42.0.1)       │
│         │ ◄──────────► │   ├─ dnsmasq (via NM shared) │
│         │              │   ├─ Flask app :80           │
│         │              │   └─ captive-portal routes   │
│         │              │                              │
│         │              │  SPI ──► Waveshare e-ink     │
└─────────┘              └──────────────────────────────┘
```

**Stack**
- AP: NetworkManager `ipv4.method shared` (handles DHCP + NAT-less routing)
- Web: Flask, single-process, bound to `0.0.0.0:80`
- E-ink: `waveshare_epd` Python module from `~/e-Paper/RaspberryPi_JetsonNano/python/lib`
- Service mgmt: `systemd`
- Persistence: SQLite (`~/purin_pi/data/purin.db`) for notes/todos
- SD card protection: `overlayroot` (read-only root, RAM overlay)

---

## 2. Repository layout (target)

```
~/purin_pi/
├── PROJECT.md                  # this file
├── README.md                   # user-facing quickstart
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py                 # Flask entrypoint
│   ├── epd.py                  # e-ink wrapper (thread-safe, panel-agnostic)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py        # / and feature endpoints
│   │   └── captive.py          # OS captive-portal probe handlers
│   ├── features/
│   │   ├── text.py
│   │   ├── draw.py
│   │   ├── qr.py
│   │   ├── notes.py
│   │   └── clock.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── draw.html
│   │   ├── qr.html
│   │   └── notes.html
│   └── static/
│       ├── style.css
│       └── draw.js
├── scripts/
│   ├── setup_ap.sh             # idempotent NetworkManager AP setup
│   ├── install_service.sh      # installs systemd unit
│   ├── enable_overlayroot.sh   # SD card protection
│   └── shutdown_button.py      # optional: GPIO shutdown handler
├── systemd/
│   └── purin-dashboard.service
└── data/                       # created at runtime (gitignored)
    └── purin.db
```

---

## 3. Implementation tasks

Each task lists: **goal**, **files to create/edit**, **acceptance test**.

### Task 1 — Detect e-ink panel and verify driver

**Goal**: Confirm which Waveshare panel is connected and that we can draw to it from Python.

**Do**:
1. List candidate modules: `ls ~/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd/`
2. Ask the user to confirm the panel model (sticker on HAT or known SKU). If unknown, default to `epd2in13_V4`.
3. Run the matching example: `python3 ~/e-Paper/RaspberryPi_JetsonNano/python/examples/<module>_test.py`
4. Record the chosen module name in `app/epd.py` as a single constant `PANEL_MODULE`.

**Acceptance**: Example script runs without exception and screen visibly updates. `PANEL_MODULE` is set.

---

### Task 2 — E-ink wrapper module

**Goal**: One place that owns the panel. Thread-safe. Always calls `sleep()` after a write. Tracks partial-refresh count and forces a full clear every 10 refreshes to prevent ghosting.

**Files**: `app/epd.py`

**API**:
```python
class Display:
    width: int            # logical width after rotation
    height: int
    def clear(self) -> None
    def show_image(self, img: PIL.Image.Image) -> None   # 1-bit, sized to (width, height)
    def show_text(self, text: str, font_size: int = 18) -> None
    def shutdown(self) -> None  # called on SIGTERM
```

**Requirements**:
- Lazy-init the panel on first use.
- Wrap all panel calls in a `threading.Lock`.
- After every `show_*`, call `epd.sleep()`.
- Counter `_partial_count`; when it hits 10, do a full `init()` + `Clear(0xFF)` before the next draw.
- Catch and log any `IOError` from SPI so a bad refresh doesn't crash the Flask app.

**Acceptance**: `python3 -c "from app.epd import Display; d=Display(); d.show_text('hello')"` updates the screen.

---

### Task 3 — Wi-Fi access point

**Goal**: Bring up a WPA2 AP named `purin-pi` on `wlan0` using NetworkManager. Idempotent — re-running the script must not duplicate connections.

**Files**: `scripts/setup_ap.sh`

**Spec**:
```bash
SSID=purin-pi
PSK=changeme-please    # read from env var PURIN_PSK if set
CON=purin-ap
```

Steps the script must perform:
1. If a connection named `$CON` exists, delete it.
2. `nmcli con add type wifi ifname wlan0 con-name $CON autoconnect yes ssid $SSID`
3. `nmcli con modify $CON 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared`
4. `nmcli con modify $CON wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK"`
5. `nmcli con up $CON`
6. Print the resulting IP (`nmcli -g IP4.ADDRESS dev show wlan0`).

**Acceptance**: After running, phone sees `purin-pi`, can connect with PSK, receives an IP in `10.42.0.0/24`, can ping `10.42.0.1`.

---

### Task 4 — Flask app skeleton

**Goal**: Minimal Flask app on `:80` that renders a homepage and accepts a text POST that updates the e-ink.

**Files**: `app/main.py`, `app/routes/dashboard.py`, `app/templates/base.html`, `app/templates/index.html`, `app/static/style.css`, `requirements.txt`

**requirements.txt**:
```
Flask>=3.0
Pillow>=10.0
qrcode[pil]>=7.4
```

**Endpoints (Task 4 scope)**:
- `GET  /`            — render `index.html` with a text input and submit button
- `POST /api/text`    — form field `msg`, calls `Display.show_text(msg)`, redirects to `/`
- `POST /api/clear`   — clears screen
- `GET  /api/status`  — JSON `{uptime, last_update, panel}`

**UX**:
- Mobile-first CSS (`viewport` meta, full-width buttons, large tap targets ≥ 44px).
- No external CDNs — everything served locally (the Pi has no internet).

**Acceptance**: From the phone connected to `purin-pi`, opening `http://10.42.0.1` shows the dashboard; submitting text updates the screen.

---

### Task 5 — Captive portal

**Goal**: When the phone joins the AP, the OS popup should auto-open the dashboard.

**Files**: `app/routes/captive.py`

**Routes** — all return `302` to `http://10.42.0.1/`:
- `/generate_204`, `/gen_204` (Android)
- `/hotspot-detect.html` (iOS)
- `/library/test/success.html` (iOS legacy)
- `/ncsi.txt`, `/connecttest.txt` (Windows, harmless)
- Catch-all for unknown hosts: a Flask `before_request` hook that, if `request.host` is not `10.42.0.1`, redirects to the dashboard.

**Also**: configure dnsmasq via NM dispatcher OR add a `dnsmasq.d` snippet that resolves `*` to `10.42.0.1`. NM `shared` already runs dnsmasq; drop `/etc/NetworkManager/dnsmasq-shared.d/captive.conf`:
```
address=/#/10.42.0.1
```

**Acceptance**: Joining the AP from Android shows the "Sign in to network" notification and opens the dashboard. iOS opens its captive sheet; if it misbehaves, document the Safari fallback in `README.md`.

---

### Task 6 — Feature: QR code generator

**Files**: `app/features/qr.py`, `app/templates/qr.html`, route `POST /api/qr` (field `data`).

Generate a QR with `qrcode`, render to a 1-bit PIL image sized to the panel, push to display. Include preset buttons for "My Wi-Fi" (uses the AP creds) and "Contact card".

**Acceptance**: Submitting text shows a scannable QR on the e-ink.

---

### Task 7 — Feature: drawing pad

**Files**: `app/templates/draw.html`, `app/static/draw.js`, route `POST /api/draw`.

- HTML `<canvas>` sized proportionally to the panel.
- Touch + mouse events, black-on-white strokes.
- "Send" button posts the canvas as a PNG (base64) to `/api/draw`.
- Server decodes, converts to 1-bit (Floyd–Steinberg dither via Pillow), pushes to display.

**Acceptance**: Drawing on phone, hitting Send, the drawing appears on e-ink within ~3s.

---

### Task 8 — Feature: notes / todos

**Files**: `app/features/notes.py`, `app/templates/notes.html`, SQLite at `data/purin.db`.

- Table `notes(id INTEGER PRIMARY KEY, body TEXT, done INTEGER, created_at TEXT)`.
- CRUD endpoints: `GET /notes`, `POST /notes`, `POST /notes/<id>/toggle`, `POST /notes/<id>/delete`.
- Button "Send list to screen" renders current open notes as a bulleted list image.

**Acceptance**: Notes persist across reboot; list renders to e-ink.

---

### Task 9 — Systemd service

**Files**: `systemd/purin-dashboard.service`, `scripts/install_service.sh`

```ini
[Unit]
Description=Purin Pi Dashboard
After=network-online.target NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/purin/purin_pi
ExecStart=/usr/bin/python3 -m app.main
Restart=always
RestartSec=3
User=root
KillSignal=SIGTERM
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
```

`install_service.sh` copies the unit, runs `daemon-reload`, enables, starts it.

**Acceptance**: `systemctl status purin-dashboard` is `active (running)` after reboot; dashboard reachable without manual launch.

---

### Task 10 — SD card protection (overlayroot)

**Files**: `scripts/enable_overlayroot.sh`

Install `overlayroot`, configure `/etc/overlayroot.conf` with `overlayroot="tmpfs"`. Document in `README.md` how to temporarily make root writable (`overlayroot-chroot`) for updates.

**Acceptance**: After reboot, `mount | grep ' / '` shows the overlay; yanking USB power 10 times in a row does not corrupt the FS.

---

### Task 11 — Boot time optimization

Disable unused services and reduce boot delay. Document each change in `scripts/optimize_boot.sh` with comments so the user can revert.

Candidates:
- `systemctl disable hciuart bluetooth` (if BT unused)
- `systemctl disable triggerhappy`
- `systemctl disable ModemManager`
- `dtoverlay=disable-bt` in `/boot/firmware/config.txt`
- `tvservice -o` at boot (HDMI off)
- `systemd-analyze blame` before/after — log results to `scripts/boot_report.txt`

**Acceptance**: `systemd-analyze` shows < 20s to `multi-user.target`.

---

### Task 12 — Graceful shutdown

**Goal**: User can't reach a shutdown UI once they unplug, so we need either a soft-shutdown button or a "park" screen update on SIGTERM.

**Files**: `app/main.py` (signal handler), optional `scripts/shutdown_button.py`.

- On SIGTERM: `Display.show_text("Safe to unplug")` then `epd.sleep()` and exit.
- Optional GPIO button (e.g. GPIO 3) wired to trigger `systemctl poweroff` — script runs as a separate systemd service.

**Acceptance**: `sudo systemctl stop purin-dashboard` leaves "Safe to unplug" on screen.

---

## 4. Coding conventions

- Python: type hints on public functions, `black`-formatted, no global state outside `app/epd.py`.
- Flask: blueprints per route file. No business logic in templates.
- Logging: `logging` module, level INFO to stdout (systemd captures it). No `print()`.
- Errors: every route returns JSON `{ok: bool, error?: str}` for `/api/*`; HTML pages flash user-visible errors.
- Never block the request thread on an e-ink refresh longer than necessary — wrap calls in `threading.Thread` if refresh > 1s.

---

## 5. Known gotchas (don't re-discover these)

- **`epd.sleep()` is mandatory** after every write or the panel degrades.
- **Full clear every ~10 partial refreshes** to fight ghosting.
- **iOS captive portal** uses a mini-browser, not Safari — sessions don't persist there. README must tell the user to dismiss it and open Safari to `http://10.42.0.1`.
- **Port 80 needs root** OR `setcap 'cap_net_bind_service=+ep' $(which python3)`. We chose root via systemd for simplicity.
- **NM `shared` mode** assigns `10.42.0.1/24` — do not hardcode a different subnet anywhere.
- **No internet on phone** while connected. Android will warn; iOS will warn. Don't try to fix it — it's by design.
- **SD corruption** is the #1 failure mode for keychain devices. Task 10 is not optional.
- **Don't refresh the clock every minute** on e-ink — limit clock updates to on-demand or every 15 min max.

---

## 6. Definition of done (v1)

- [ ] Plug Pi into phone, wait < 30s, AP `purin-pi` appears.
- [ ] Phone joins, captive sheet opens dashboard automatically (Android) or via Safari (iOS).
- [ ] Can send text, QR, drawing, and a notes list to the screen.
- [ ] Notes persist across reboots.
- [ ] Service auto-starts and auto-restarts on crash.
- [ ] Root FS is read-only (overlay); unclean unplug is survivable.
- [ ] `README.md` documents: first-boot setup, changing the Wi-Fi password, updating the app, and the iOS Safari workaround.

---

## 7. Out of scope / future ideas

- BLE companion app instead of Wi-Fi AP (faster connect, no captive portal pain)
- Battery + power-management HAT for always-on operation
- OTA updates via a "plug into home Wi-Fi" mode toggle
- Multi-screen layouts / widgets framework
- Image upload from phone gallery with auto-dither preview
