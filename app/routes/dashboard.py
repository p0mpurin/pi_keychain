"""Dashboard pages and APIs."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.epd import PANEL_MODULE, get_display
from app.features import clock as clock_feature
from app.features import draw as draw_feature
from app.features import notes as notes_feature
from app.features import qr as qr_feature
from app.features import text as text_feature

logger = logging.getLogger(__name__)

bp = Blueprint("dashboard", __name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "purin.db"

_db_conn = notes_feature.connect(DB_PATH)
_db_lock = threading.Lock()

_APP_START = time.time()


def _wifi_qr_payload() -> str:
    ssid = os.environ.get("PURIN_AP_SSID", "purin-pi")
    psk = os.environ.get("PURIN_PSK", "changeme-please")
    return f"WIFI:T:WPA;S:{ssid};P:{psk};;"


def _schedule_display(work, *, synchronous: bool = False) -> None:
    """Run display IO off the Flask request thread unless synchronous (signals)."""

    def runner() -> None:
        logger.info("Display worker started")
        try:
            work()
        except Exception:
            logger.exception("Display worker failed")
        else:
            logger.info("Display worker finished OK")

    if synchronous:
        runner()
    else:
        threading.Thread(target=runner, daemon=True).start()


def _json_err(message: str, status: int = 400) -> tuple[dict[str, object], int]:
    return {"ok": False, "error": message}, status


@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/draw")
def draw_page():
    disp = get_display()
    try:
        w, h = disp.probe_size()
    except Exception:
        w, h = 250, 122
    return render_template("draw.html", panel_w=w, panel_h=h)


@bp.route("/qr")
def qr_page():
    wifi_payload = _wifi_qr_payload()
    contact_preset = (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        "FN:Purin Pi\r\n"
        "NOTE:keychain dashboard\r\n"
        "END:VCARD\r\n"
    )
    return render_template(
        "qr.html",
        wifi_payload=wifi_payload,
        contact_preset=contact_preset,
    )


@bp.route("/notes", methods=["GET", "POST"])
def notes_page():
    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "add":
            body = request.form.get("body", "").strip()
            if body:
                with _db_lock:
                    notes_feature.add_note(_db_conn, body)
            else:
                flash("Note cannot be empty.", "error")
        return redirect(url_for("dashboard.notes_page"))

    with _db_lock:
        rows = notes_feature.list_notes(_db_conn, include_done=True)
    return render_template("notes.html", notes=rows)


@bp.route("/notes/<int:note_id>/toggle", methods=["POST"])
def notes_toggle(note_id: int):
    with _db_lock:
        ok = notes_feature.toggle_note(_db_conn, note_id)
    if not ok:
        flash("Note not found.", "error")
    return redirect(url_for("dashboard.notes_page"))


@bp.route("/notes/<int:note_id>/delete", methods=["POST"])
def notes_delete(note_id: int):
    with _db_lock:
        notes_feature.delete_note(_db_conn, note_id)
    return redirect(url_for("dashboard.notes_page"))


@bp.route("/notes/send_screen", methods=["POST"])
def notes_send_screen():
    disp = get_display()

    def work() -> None:
        disp.probe_size()
        with _db_lock:
            lines = notes_feature.lines_for_display(_db_conn)
        if not lines:
            lines = ["(no open notes)"]
        img = text_feature.render_multiline(lines, disp.width, disp.height)
        disp.show_image(img)

    _schedule_display(work)
    flash("Sent open notes to the display.", "info")
    return redirect(url_for("dashboard.notes_page"))


@bp.post("/api/text")
def api_text():
    msg = request.form.get("msg", "").strip()
    if not msg:
        return _json_err("msg required")
    disp = get_display()
    _schedule_display(lambda: disp.show_text(msg))
    return redirect(url_for("dashboard.index"))


@bp.post("/api/clear")
def api_clear():
    disp = get_display()
    _schedule_display(lambda: disp.clear())
    if request.accept_mimetypes.best == "application/json":
        return {"ok": True}
    return redirect(url_for("dashboard.index"))


@bp.get("/api/status")
def api_status():
    disp = get_display()
    uptime_s = max(0.0, time.time() - _APP_START)
    last = disp.last_update_epoch
    return {
        "ok": True,
        "uptime": uptime_s,
        "last_update": last,
        "panel": PANEL_MODULE,
    }


@bp.post("/api/qr")
def api_qr():
    data = request.form.get("data", "").strip()
    if not data:
        body_json = request.get_json(silent=True) or {}
        data = str(body_json.get("data", "")).strip()
    if not data:
        return _json_err("data required")

    disp = get_display()

    def work() -> None:
        disp.probe_size()
        img = qr_feature.qr_image_for_panel(data, disp.width, disp.height)
        disp.show_image(img)

    _schedule_display(work)
    if request.accept_mimetypes.best == "application/json":
        return {"ok": True}
    return redirect(url_for("dashboard.qr_page"))


@bp.post("/api/draw")
def api_draw():
    payload = request.get_json(silent=True) or {}
    raw_b64 = payload.get("image") or ""
    if not raw_b64:
        return _json_err("image base64 required")

    disp = get_display()
    try:
        disp.probe_size()
    except Exception as e:
        logger.warning("Panel not available: %s", e)
        return _json_err("display unavailable", status=503)

    img = draw_feature.png_base64_to_epd_image(raw_b64, disp.width, disp.height)
    if img is None:
        return _json_err("invalid image")

    _schedule_display(lambda: disp.show_image(img))
    return {"ok": True}


@bp.post("/api/clock")
def api_clock():
    tz = request.form.get("tz") or request.args.get("tz") or "UTC"
    disp = get_display()

    def work() -> None:
        disp.probe_size()
        img = clock_feature.render_clock_image(disp.width, disp.height, tz_name=tz)
        disp.show_image(img)

    _schedule_display(work)
    if request.accept_mimetypes.best == "application/json":
        return {"ok": True}
    return redirect(url_for("dashboard.index"))
