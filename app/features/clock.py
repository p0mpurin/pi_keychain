"""On-demand clock display (avoid frequent e-ink refreshes)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


def render_clock_image(
    width: int,
    height: int,
    tz_name: str = "UTC",
    font_size: int = 28,
) -> Image.Image:
    """Single-frame clock image for manual refresh only."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz).strftime("%Y-%m-%d\n%H:%M:%S")
    img = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size
        )
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((8, 8), now, fill=0, font=font, spacing=6)
    return img
