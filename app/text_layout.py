"""Text rendering for e-paper: word-wrap, auto font-fit, alignment."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont, ImageOps

# ── defaults ──────────────────────────────────────────────────────────────────

DEFAULT_TEXT_LAYOUT: dict = {
    "font_size": 0,          # 0 = auto-fit
    "align_h": "left",
    "align_v": "top",
    "margin_x": 6,
    "margin_y": 6,
    "line_spacing": 3,
    "flip_horizontal": False,
    "flip_vertical": False,
}

ALIGN_H = frozenset(("left", "center", "right"))
ALIGN_V = frozenset(("top", "middle", "bottom"))

_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_MONO  = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


# ── helpers ───────────────────────────────────────────────────────────────────

def _clamp_int(v: object, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return lo


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in (_FONT_PATH, _FONT_MONO):
        try:
            return ImageFont.truetype(path, max(8, size))
        except OSError:
            pass
    return ImageFont.load_default()


def _word_wrap(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_px: int) -> str:
    """Wrap text so each rendered line is at most max_px wide."""
    out_lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        words = raw_line.split(" ")
        cur = ""
        for word in words:
            candidate = (cur + " " + word).lstrip() if cur else word
            if draw.textlength(candidate, font=font) <= max_px:
                cur = candidate
            else:
                if cur:
                    out_lines.append(cur)
                # word itself may be wider than max_px — accept it as-is
                cur = word
        out_lines.append(cur)
    return "\n".join(out_lines)


def _block_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    spacing: int,
    align: str,
) -> tuple[int, int]:
    lx, ly, rx, by = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=align)
    return max(1, rx - lx), max(1, by - ly)


def _auto_font_size(
    text: str,
    inner_w: int,
    inner_h: int,
    spacing: int,
    align: str,
    *,
    lo: int = 8,
    hi: int = 60,
) -> tuple[int, str]:
    """Binary-search for the largest font size where wrapped text fits inner_w × inner_h."""
    # Use a scratch image for measurement only
    scratch = Image.new("1", (inner_w + 2, inner_h + 2), 255)
    draw = ImageDraw.Draw(scratch)

    best_size, best_text = lo, text
    lo_s, hi_s = lo, hi
    while lo_s <= hi_s:
        mid = (lo_s + hi_s) // 2
        font = _load_font(mid)
        wrapped = _word_wrap(text, draw, font, inner_w)
        tw, th = _block_size(draw, wrapped, font, spacing, align)
        if tw <= inner_w and th <= inner_h:
            best_size, best_text = mid, wrapped
            lo_s = mid + 1
        else:
            hi_s = mid - 1
    return best_size, best_text


# ── public API ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TextLayoutProfile:
    font_size: int       # 0 = auto
    align_h: str
    align_v: str
    margin_x: int
    margin_y: int
    line_spacing: int
    flip_horizontal: bool
    flip_vertical: bool

    @staticmethod
    def from_dict(raw: dict | None) -> TextLayoutProfile:
        d = {**DEFAULT_TEXT_LAYOUT, **(raw or {})}
        ah = str(d.get("align_h", "left")).lower()
        if ah not in ALIGN_H:
            ah = "left"
        av = str(d.get("align_v", "top")).lower()
        if av not in ALIGN_V:
            av = "top"
        return TextLayoutProfile(
            font_size=_clamp_int(d.get("font_size", 0), 0, 72),
            align_h=ah,
            align_v=av,
            margin_x=_clamp_int(d.get("margin_x", 6), 0, 120),
            margin_y=_clamp_int(d.get("margin_y", 6), 0, 120),
            line_spacing=_clamp_int(d.get("line_spacing", 3), 0, 24),
            flip_horizontal=bool(d.get("flip_horizontal", False)),
            flip_vertical=bool(d.get("flip_vertical", False)),
        )


def render_plaintext(
    text: str,
    panel_w: int,
    panel_h: int,
    profile: TextLayoutProfile,
    *,
    font_size: int | None = None,
) -> Image.Image:
    """Render text into a 1-bit panel-sized image with word-wrap and alignment."""
    if not text.strip():
        return Image.new("1", (panel_w, panel_h), 255)

    mx, my = profile.margin_x, profile.margin_y
    inner_w = max(16, panel_w - 2 * mx)
    inner_h = max(16, panel_h - 2 * my)
    spacing  = profile.line_spacing
    align    = profile.align_h

    # Scratch draw for measurement
    scratch = Image.new("1", (panel_w, panel_h), 255)
    draw    = ImageDraw.Draw(scratch)

    req_size = font_size if font_size is not None else profile.font_size

    if req_size and req_size > 0:
        # Fixed size requested — just word-wrap, no auto-resize
        font    = _load_font(req_size)
        wrapped = _word_wrap(text, draw, font, inner_w)
    else:
        # Auto-fit: find largest size that fits
        size, wrapped = _auto_font_size(text, inner_w, inner_h, spacing, align)
        font = _load_font(size)

    # Measure the final block
    bw, bh = _block_size(draw, wrapped, font, spacing, align)

    # Horizontal anchor
    if align == "center":
        x = mx + (inner_w - bw) // 2
    elif align == "right":
        x = mx + inner_w - bw
    else:
        x = mx

    # Vertical anchor
    if profile.align_v == "middle":
        y = my + (inner_h - bh) // 2
    elif profile.align_v == "bottom":
        y = my + inner_h - bh
    else:
        y = my

    # Correct for textbbox origin offset
    lx, ly, _, _ = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=spacing, align=align)

    img  = Image.new("1", (panel_w, panel_h), 255)
    draw = ImageDraw.Draw(img)
    draw.multiline_text(
        (x - lx, y - ly),
        wrapped,
        fill=0,
        font=font,
        spacing=spacing,
        align=align,
    )

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
    return render_plaintext("\n".join(lines) if lines else "", panel_w, panel_h, profile, font_size=font_size)
