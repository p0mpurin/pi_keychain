"""Persisted display settings — orientation mode, text layout, invert."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.text_layout import DEFAULT_TEXT_LAYOUT

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR      = _PROJECT_ROOT / "data"
SETTINGS_PATH = DATA_DIR / "display_settings.json"

_VALID_ROT = frozenset((0, 90, 180, 270))

# ── Mode presets (ports-on-top / upside-down mount) ───────────────────────────
# The Waveshare 2.13" driver native: width=122 height=250 (portrait).
# Holding with ports on top means the natural image is upside down.
#   horizontal → rotate 270° → logical 250×122 wide, right-side-up
#   vertical   → rotate 180° → logical 122×250 tall, right-side-up

MODES: dict[str, dict[str, int]] = {
    "horizontal": {"rotate": 270, "coordinate_twist_deg": 0},
    "vertical":   {"rotate": 180, "coordinate_twist_deg": 0},
}

DEFAULT_MODE = "horizontal"


# ── low-level helpers ─────────────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw) % 360
    except ValueError:
        return default
    return v if v in _VALID_ROT else default


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v not in ("0", "false", "no", "off")


def read_settings_file() -> dict:
    try:
        raw  = SETTINGS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)


# ── effective values ──────────────────────────────────────────────────────────

def effective_rotate() -> int:
    data = read_settings_file()
    r = data.get("rotate")
    if r is not None:
        try:
            v = int(r) % 360
            if v in _VALID_ROT:
                return v
        except (TypeError, ValueError):
            pass
    return _env_int("PURIN_EPD_ROTATE", 270)   # default to horizontal


def effective_invert() -> bool:
    data = read_settings_file()
    if "invert" in data:
        return bool(data["invert"])
    return _env_bool("PURIN_EPD_INVERT")


def effective_coordinate_twist_deg() -> int:
    r = read_settings_file().get("coordinate_twist_deg")
    if r is not None:
        try:
            v = int(r) % 360
            if v in _VALID_ROT:
                return v
        except (TypeError, ValueError):
            pass
    return _env_int("PURIN_COORDINATE_TWIST_DEG", 0)


def effective_mode() -> str:
    data = read_settings_file()
    m = str(data.get("mode", "")).lower()
    return m if m in MODES else DEFAULT_MODE


def effective_correct_180() -> bool:
    """Whether to flip the raster 180° — corrects for upside-down mount (ports on top)."""
    data = read_settings_file()
    if "correct_180" in data:
        return bool(data["correct_180"])
    return True  # default: ports on top


def effective_text_layout_dict() -> dict[str, Any]:
    return {**DEFAULT_TEXT_LAYOUT, **read_settings_file().get("text", {})}


# ── save helpers ──────────────────────────────────────────────────────────────

def save_mode(mode: str, invert: bool, *, font_size: int = 0, correct_180: bool = True) -> None:
    """Apply a named mode preset; update invert + optional font_size."""
    if mode not in MODES:
        mode = DEFAULT_MODE
    preset = MODES[mode]
    data = read_settings_file()
    data["mode"]                 = mode
    data["rotate"]               = preset["rotate"]
    data["coordinate_twist_deg"] = preset["coordinate_twist_deg"]
    data["invert"]               = bool(invert)
    data["correct_180"]          = bool(correct_180)
    text = {**DEFAULT_TEXT_LAYOUT, **data.get("text", {})}
    text["font_size"] = max(0, int(font_size))
    data["text"] = text
    _atomic_write(data)


def save_settings(
    rotate: int,
    invert: bool,
    *,
    coordinate_twist_deg: int | None = None,
) -> None:
    rotate = int(rotate) % 360
    if rotate not in _VALID_ROT:
        rotate = 0
    data = read_settings_file()
    data["rotate"] = rotate
    data["invert"] = bool(invert)
    if coordinate_twist_deg is not None:
        t = int(coordinate_twist_deg) % 360
        data["coordinate_twist_deg"] = t if t in _VALID_ROT else 0
    if "text" not in data:
        data["text"] = {**DEFAULT_TEXT_LAYOUT}
    _atomic_write(data)


def save_text_layout(updates: dict[str, Any]) -> None:
    if not isinstance(updates, dict):
        return
    data   = read_settings_file()
    merged = {**DEFAULT_TEXT_LAYOUT, **data.get("text", {})}
    for key in DEFAULT_TEXT_LAYOUT:
        if key in updates:
            merged[key] = updates[key]
    data["text"] = merged
    _atomic_write(data)
