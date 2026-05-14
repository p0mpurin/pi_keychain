"""User-tunable text block layout for e-paper (alignment, margins, optional flips)."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont, ImageOps


@dataclass(frozen=True)
class TextLayoutProfile:
    align_h: str  # left | center | right
    align_v: str  # top | middle | bottom
    margin_x: int
    margin_y: int
    font_size: int
    line_spacing: int
    flip_horizontal: bool
    flip_vertical: bool
    reverse_chars: bool

    @staticmethod
    def from_dict(raw: dict | None) -> TextLayoutProfile:
        d = DEFAULT_TEXT_LAYOUT.copy()
        if isinstance(raw, dict):
            d.update({k: raw[k] for k in d if k in raw})
        ah = str(d["align_h"]).lower()
        av = str(d["align_v"]).lower()
        if ah not in ALIGN_H:
            ah = "left"
        if av not in ALIGN_V:
            av = "top"
        return TextLayoutProfile(
            align_h=ah,
            align_v=av,
            margin_x=_clamp_int(d.get("margin_x", 4), 0, 160),
            margin_y=_clamp_int(d.get("margin_y", 4), 0, 160),
            font_size=_clamp_int(d.get("font_size", 18), 8, 72),
            line_spacing=_clamp_int(d.get("line_spacing", 4), 0, 32),
            flip_horizontal=bool(d.get("flip_horizontal", False)),
            flip_vertical=bool(d.get("flip_vertical", False)),
            reverse_chars=bool(d.get("reverse_chars", False)),
        )


ALIGN_H = frozenset(("left", "center", "right"))
ALIGN_V = frozenset(("top", "middle", "bottom"))

DEFAULT_TEXT_LAYOUT: dict = {
    "align_h": "left",
    "align_v": "top",
    "margin_x": 4,
    "margin_y": 4,
    "font_size": 18,
    "line_spacing": 4,
    "flip_horizontal": False,
    "flip_vertical": False,
    "reverse_chars": False,
}


def _clamp_int(v: object, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, n))


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _apply_char_transform(text: str, profile: TextLayoutProfile) -> str:
    if not profile.reverse_chars:
        return text
    parts = text.replace("\r\n", "\n").split("\n")
    return "\n".join(line[::-1] for line in parts)


def _box_xy(
    panel_w: int,
    panel_h: int,
    tw: int,
    th: int,
    profile: TextLayoutProfile,
) -> tuple[int, int]:
    mx, my = profile.margin_x, profile.margin_y
    inner_w = max(1, panel_w - 2 * mx)
    inner_h = max(1, panel_h - 2 * my)
    tw_eff = min(tw, inner_w)
    th_eff = min(th, inner_h)

    if profile.align_h == "left":
        x_left = mx
    elif profile.align_h == "center":
        x_left = mx + (inner_w - tw_eff) // 2
    else:
        x_left = mx + inner_w - tw_eff

    if profile.align_v == "top":
        y_top = my
    elif profile.align_v == "middle":
        y_top = my + (inner_h - th_eff) // 2
    else:
        y_top = my + inner_h - th_eff

    return int(x_left), int(y_top)


def render_plaintext(
    text: str,
    panel_w: int,
    panel_h: int,
    profile: TextLayoutProfile,
    *,
    font_size: int | None = None,
) -> Image.Image:
    """Paint multiline PIL text positioned by profile; optional font_size overrides profile."""
    body = _apply_char_transform(text, profile)
    size = profile.font_size if font_size is None else _clamp_int(font_size, 8, 72)
    font = _load_font(size)
    spacing = profile.line_spacing
    img = Image.new("1", (panel_w, panel_h), 255)
    draw = ImageDraw.Draw(img)

    lx, ly, rx, by = draw.multiline_textbbox(
        (0, 0),
        body,
        font=font,
        spacing=spacing,
        align=profile.align_h,
    )
    tw, th = max(1, rx - lx), max(1, by - ly)
    x0, y0 = _box_xy(panel_w, panel_h, tw, th, profile)
    ox = x0 - lx
    oy = y0 - ly

    draw.multiline_text(
        (ox, oy),
        body,
        fill=0,
        font=font,
        spacing=spacing,
        align=profile.align_h,
    )

    if profile.flip_horizontal or profile.flip_vertical:
        if profile.flip_horizontal:
            img = ImageOps.mirror(img)
        if profile.flip_vertical:
            img = ImageOps.flip(img)
    return img


def render_multiline(
    lines: list[str],
    panel_w: int,
    panel_h: int,
    profile: TextLayoutProfile,
    *,
    font_size: int | None = None,
) -> Image.Image:
    text = "\n".join(lines) if lines else ""
    return render_plaintext(text, panel_w, panel_h, profile, font_size=font_size)

