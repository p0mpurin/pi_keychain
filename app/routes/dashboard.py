"""Dashboard pages and APIs."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.display_settings import (
    MODES,
    effective_mode,
    effective_text_layout_dict,
    save_mode,
    save_settings,
    save_text_layout,
)
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
_display_queue_lock = threading.Lock()

_APP_START = time.time()


def _wifi_qr_payload() -> str:
    ssid = os.environ.get("PURIN_AP_SSID", "purin-pi")
    psk = os.environ.get("PURIN_PSK", "changeme-please")
    return f"WIFI:T:WPA;S:{ssid};P:{psk};;"


def _parse_rotate_env_val(raw: object | None) -> int | None:
    if raw is None:
        return None
    try:
        v = int(raw) % 360
    except (TypeError, ValueError):
        return None
    return v if v in {0, 90, 180, 270} else None


def _parse_invert(raw: object | None, *, form_checkbox: bool) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    s = str(raw).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    if form_checkbox:
        return s == "on"
    return False


def _intrinsic_canvas_size(panel_w: int, panel_h: int, *, target_max_edge: int = 720) -> tuple[int, int]:
    """Interior canvas pixels with same aspect as logical panel (avoids distorted X/Y in draw export)."""
    pw, ph = max(16, int(panel_w)), max(16, int(panel_h))
    scale = target_max_edge / max(pw, ph)
    return max(48, round(pw * scale)), max(48, round(ph * scale))


def _schedule_display(work, *, synchronous: bool = False) -> None:
    """Run display IO off the Flask request thread unless synchronous (signals)."""

    def run_work() -> None:
        logger.info("Display worker started")
        try:
            work()
        except Exception:
            logger.exception("Display worker failed")
        else:
            logger.info("Display worker finished OK")

    if synchronous:
        run_work()
        return

    def thread_main() -> None:
        logger.info("Display job queued (waiting for single-flight lock)")
        with _display_queue_lock:
            run_work()

    threading.Thread(target=thread_main, daemon=True).start()


def _json_err(message: str, status: int = 400) -> tuple[dict[str, object], int]:
    return {"ok": False, "error": message}, status


@bp.route("/")
def index():
    disp = get_display()
    return render_template(
        "index.html",
        epd_rotate=disp.rotation_degrees,
        epd_invert=disp.invert_bits,
        epd_mode=effective_mode(),
        text_layout=effective_text_layout_dict(),
    )


def _coerce_text_layout_payload(src: dict) -> dict:
    def g_int(key: str, lo: int, hi: int, default: int) -> int:
        try:
            v = int(src.get(key, default))
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, v))

    ah = str(src.get("align_h", "left")).lower()
    if ah not in ("left", "center", "right"):
        ah = "left"
    av = str(src.get("align_v", "top")).lower()
    if av not in ("top", "middle", "bottom"):
        av = "top"
    def as_bool(key: str) -> bool:
        raw = src.get(key)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return raw != 0
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return False

    return {
        "align_h": ah,
        "align_v": av,
        "margin_x": g_int("margin_x", 0, 120, 6),
        "margin_y": g_int("margin_y", 0, 120, 6),
        "font_size": g_int("font_size", 0, 72, 0),   # 0 = auto
        "line_spacing": g_int("line_spacing", 0, 24, 3),
        "flip_horizontal": as_bool("flip_horizontal"),
        "flip_vertical": as_bool("flip_vertical"),
    }


def _text_layout_from_form() -> dict:
    return _coerce_text_layout_payload(
        {
            "align_h": request.form.get("align_h"),
            "align_v": request.form.get("align_v"),
            "margin_x": request.form.get("margin_x"),
            "margin_y": request.form.get("margin_y"),
            "font_size": request.form.get("font_size"),
            "line_spacing": request.form.get("line_spacing"),
            "flip_horizontal": request.form.get("flip_horizontal") == "on",
            "flip_vertical": request.form.get("flip_vertical") == "on",
        }
    )


@bp.route("/api/text_layout", methods=["GET", "POST"])
def api_text_layout():
    if request.method == "GET":
        return {"ok": True, "text": effective_text_layout_dict()}

    ct = (request.content_type or "").split(";")[0].strip().lower()
    payload = request.get_json(silent=True)

    if ct == "application/json" and isinstance(payload, dict):
        layout = _coerce_text_layout_payload(payload)
    else:
        layout = _text_layout_from_form()

    save_text_layout(layout)

    if ct == "application/json" and isinstance(payload, dict):
        return {"ok": True, "text": effective_text_layout_dict()}

    flash("Saved text layout.", "info")
    return redirect(url_for("dashboard.index"))


@bp.post("/api/mode")
def api_mode():
    """Set horizontal/vertical mode + invert + font_size in one click."""
    ct      = (request.content_type or "").split(";")[0].strip().lower()
    payload = request.get_json(silent=True) if ct == "application/json" else None

    if isinstance(payload, dict):
        mode      = str(payload.get("mode", "horizontal")).lower()
        inv       = bool(payload.get("invert", False))
        font_size = int(payload.get("font_size", 0))
    else:
        mode      = str(request.form.get("mode", "horizontal")).lower()
        inv       = request.form.get("invert") == "on"
        try:
            font_size = int(request.form.get("font_size", 0))
        except (TypeError, ValueError):
            font_size = 0

    if mode not in MODES:
        mode = "horizontal"

    preset = MODES[mode]
    save_mode(mode, inv, font_size=font_size)

    disp = get_display()
    disp.set_rotation(preset["rotate"])
    disp.set_invert(inv)
    disp.set_coordinate_twist_degrees(preset["coordinate_twist_deg"])

    if isinstance(payload, dict):
        return {"ok": True, "mode": mode, "rotate": preset["rotate"], "invert": inv}

    flash(f"Mode set to {mode}.", "info")
    return redirect(url_for("dashboard.index"))


@bp.route("/api/display_settings", methods=["GET", "POST"])
def api_display_settings():
    disp = get_display()
    if request.method == "GET":
        return {
            "ok": True,
            "rotate": disp.rotation_degrees,
            "invert": disp.invert_bits,
            "coordinate_twist_deg": disp.coordinate_twist_degrees,
            "text": effective_text_layout_dict(),
        }

    ct = (request.content_type or "").split(";")[0].strip().lower()
    payload = request.get_json(silent=True)

    if ct == "application/json" and isinstance(payload, dict):
        if "rotate" not in payload:
            return _json_err("rotate required")
        rot = _parse_rotate_env_val(payload.get("rotate"))
        if rot is None:
            return _json_err("rotate must be 0, 90, 180, or 270")
        inv = disp.invert_bits
        if "invert" in payload:
            inv = bool(payload["invert"])
        if "coordinate_twist_deg" in payload:
            twist = _parse_rotate_env_val(payload.get("coordinate_twist_deg"))
            if twist is None:
                return _json_err("coordinate_twist_deg must be 0, 90, 180, or 270")
        else:
            twist = disp.coordinate_twist_degrees
    else:
        rot = _parse_rotate_env_val(request.form.get("rotate"))
        if rot is None:
            flash("Choose a valid rotation.", "error")
            return redirect(url_for("dashboard.index"))
        inv = request.form.get("invert") == "on"
        twist = _parse_rotate_env_val(request.form.get("coordinate_twist_deg"))
        if twist is None:
            twist = 0

    save_settings(rot, inv, coordinate_twist_deg=twist)
    disp.set_rotation(rot)
    disp.set_invert(inv)
    disp.set_coordinate_twist_degrees(twist)

    if ct == "application/json" and isinstance(payload, dict):
        return {
            "ok": True,
            "rotate": rot,
            "invert": inv,
            "coordinate_twist_deg": twist,
            "text": effective_text_layout_dict(),
        }

    flash("Saved display orientation.", "info")
    return redirect(url_for("dashboard.index"))


@bp.route("/draw")
def draw_page():
    disp = get_display()
    try:
        w, h = disp.probe_size()
    except Exception:
        w, h = 250, 122
    cw, ch = _intrinsic_canvas_size(w, h)
    return render_template("draw.html", panel_w=w, panel_h=h, canvas_w=cw, canvas_h=ch)


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
        "display": {
            "rotate": disp.rotation_degrees,
            "invert": disp.invert_bits,
            "coordinate_twist_deg": disp.coordinate_twist_degrees,
            "text": effective_text_layout_dict(),
        },
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
