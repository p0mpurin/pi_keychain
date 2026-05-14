"""Persisted e-paper orientation + optional text-layout block (`data/display_settings.json`)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.text_layout import DEFAULT_TEXT_LAYOUT

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = _PROJECT_ROOT / "data"
SETTINGS_PATH = DATA_DIR / "display_settings.json"

_VALID_ROT = frozenset((0, 90, 180, 270))


def _env_rotate() -> int:
    raw = os.environ.get("PURIN_EPD_ROTATE", "").strip()
    if not raw:
        return 0
    try:
        v = int(raw) % 360
    except ValueError:
        return 0
    return v if v in _VALID_ROT else 0


def _env_invert() -> bool:
    v = os.environ.get("PURIN_EPD_INVERT", "0").strip().lower()
    return v not in ("0", "false", "no", "off", "")


def read_settings_file() -> dict:
    try:
        raw = SETTINGS_PATH.read_text(encoding="utf-8")
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
    return _env_rotate()


def effective_invert() -> bool:
    data = read_settings_file()
    if "invert" in data:
        return bool(data["invert"])
    return _env_invert()


def effective_text_layout_dict() -> dict[str, Any]:
    """Merged defaults + saved `text` object."""
    return {**DEFAULT_TEXT_LAYOUT, **read_settings_file().get("text", {})}


def _env_twist_deg() -> int:
    raw = os.environ.get("PURIN_COORDINATE_TWIST_DEG", "").strip()
    if not raw:
        return 0
    try:
        v = int(raw) % 360
    except ValueError:
        return 0
    return v if v in _VALID_ROT else 0


def effective_coordinate_twist_deg() -> int:
    """Extra CW rotation applied to raster *before* panel rotation — fixes swapped X/Y on some setups."""
    r = read_settings_file().get("coordinate_twist_deg")
    if r is not None:
        try:
            v = int(r) % 360
            if v in _VALID_ROT:
                return v
        except (TypeError, ValueError):
            pass
    return _env_twist_deg()


def save_settings(
    rotate: int,
    invert: bool,
    *,
    coordinate_twist_deg: int | None = None,
) -> None:
    """Rotation + polarity; optional twist. Preserves `text` block when present."""
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
    """Merge validated keys under `text`; keeps orientation keys."""
    if not isinstance(updates, dict):
        return
    data = read_settings_file()
    merged = {**DEFAULT_TEXT_LAYOUT, **data.get("text", {})}
    for key in DEFAULT_TEXT_LAYOUT:
        if key in updates:
            merged[key] = updates[key]
    data["text"] = merged
    _atomic_write(data)
