"""Text rendering helpers for e-ink."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def render_multiline(
    lines: list[str],
    width: int,
    height: int,
    font_size: int = 16,
) -> Image.Image:
    """Render bullet-style lines into a 1-bit image."""
    img = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size
        )
    except OSError:
        font = ImageFont.load_default()
    y = 6
    margin = 6
    line_h = font_size + 4
    for line in lines:
        if y + line_h > height:
            draw.text((margin, y), "…", fill=0, font=font)
            break
        draw.text((margin, y), line, fill=0, font=font)
        y += line_h
    return img
