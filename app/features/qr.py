"""QR code rendering for the panel."""

from __future__ import annotations

import qrcode
from PIL import Image


def qr_image_for_panel(data: str, width: int, height: int) -> Image.Image:
    """Create a scannable QR as a 1-bit image fitted to the panel."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img_rgb = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    # Fit inside panel preserving aspect ratio
    iw, ih = img_rgb.size
    scale = min((width - 4) / iw, (height - 4) / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    img_rgb = img_rgb.resize((nw, nh), Image.Resampling.NEAREST)
    out = Image.new("RGB", (width, height), "white")
    ox = (width - nw) // 2
    oy = (height - nh) // 2
    out.paste(img_rgb, (ox, oy))
    return out.convert("1")
