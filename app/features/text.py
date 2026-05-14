"""Text rendering helpers for e-ink."""

from __future__ import annotations

from PIL.Image import Image

from app.display_settings import effective_text_layout_dict
from app.text_layout import TextLayoutProfile, render_multiline as _render_ml


def layout_profile(bound: dict | None = None) -> TextLayoutProfile:
    if bound is None:
        bound = effective_text_layout_dict()
    return TextLayoutProfile.from_dict(bound)


def render_multiline(
    lines: list[str],
    width: int,
    height: int,
    *,
    font_size: int | None = None,
    profile: TextLayoutProfile | None = None,
) -> Image:
    p = profile or layout_profile()
    return _render_ml(lines, width, height, p, font_size=font_size)
