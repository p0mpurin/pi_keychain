"""Decode sketch uploads and dither for e-ink."""

from __future__ import annotations

import base64
import binascii
import io
import logging

from PIL import Image

logger = logging.getLogger(__name__)


def png_base64_to_epd_image(raw_b64: str, width: int, height: int) -> Image.Image | None:
    """Decode a PNG data URL or raw base64; return 1-bit image sized to panel."""
    payload = raw_b64.strip()
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    try:
        blob = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as e:
        logger.warning("Invalid base64 sketch: %s", e)
        return None
    try:
        img = Image.open(io.BytesIO(blob)).convert("RGB")
    except OSError as e:
        logger.warning("Invalid PNG sketch: %s", e)
        return None
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    return img.convert("L").convert("1", dither=Image.Dither.FLOYDSTEINBERG)
