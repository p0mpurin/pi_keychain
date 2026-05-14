"""Persisted e-paper orientation (rotation + invert). Overrides env when data/display_settings.json exists."""

from __future__ import annotations

import json
import os
from pathlib import Path

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


def save_settings(rotate: int, invert: bool) -> None:
    rotate = int(rotate) % 360
    if rotate not in _VALID_ROT:
        rotate = 0
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"rotate": rotate, "invert": bool(invert)}
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)
