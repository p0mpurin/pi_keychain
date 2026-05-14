"""Thread-safe e-ink display wrapper (Waveshare via ~/e-Paper).

Official reference for **`waveshare_epd.epd2in13_V4`** (class **`EPD`**) —
`RaspberryPi_JetsonNano/python/examples/epd_2in13_V4_test.py` in waveshareteam/e-Paper:

- **`epd.init()`** then **`epd.Clear(0xFF)`**, then **`epd.init()`** again immediately before **`epd.display(epd.getbuffer(image))`**.
- While cycling images the demo uses **`time.sleep()`** on the Pi only — **`epd.sleep()`** is for **power‑off / deep sleep**.
- **`epd.sleep()`** sends deep‑sleep commands and **`epdconfig.module_exit()`** (releases SPI/GPIO); calling it after **every**
  frame often matches “nothing until I pushed twice” / flaky first updates.
- PIL frames in Waveshare’s demo use **`Image.new('1', (epd.height, epd.width), 255)`** (250×122); **`getbuffer()`** also accepts **`(122, 250)`** and handles rotation internally.

Tune with env **`PURIN_EPD_SLEEP_AFTER_DRAW`** (**off by default**, matching the stock demo).
**Landscape / polarity:** saved in **`data/display_settings.json`** when you use the dashboard (overrides env on restart). Env fallbacks:
**`PURIN_EPD_ROTATE`**, **`PURIN_EPD_INVERT`**, **`PURIN_COORDINATE_TWIST_DEG`** (0/90/180/270; extra raster rotation before panel rotation).

See: https://github.com/waveshareteam/e-Paper/blob/master/RaspberryPi_JetsonNano/python/examples/epd_2in13_V4_test.py

"""

from __future__ import annotations

import importlib
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from app.display_settings import (
    effective_coordinate_twist_deg,
    effective_invert,
    effective_rotate,
    effective_text_layout_dict,
)
from app.text_layout import TextLayoutProfile, render_plaintext

logger = logging.getLogger(__name__)

# Task 1: confirm on hardware via examples; default until panel is verified.
PANEL_MODULE = "epd2in13_V4"


def _epaper_lib_candidates() -> list[Path]:
    """Paths to try for Waveshare's `waveshare_epd` package (order matters)."""
    rel = Path("e-Paper/RaspberryPi_JetsonNano/python/lib")
    raw = os.environ.get("PURIN_EPAPER_LIB", "").strip()
    if raw:
        return [Path(raw).expanduser().resolve()]
    home = Path.home()
    extra = []
    eh = os.environ.get("PURIN_EPAPER_HOME", "").strip()
    if eh:
        extra.append(Path(eh).expanduser() / "RaspberryPi_JetsonNano/python/lib")
    return [
        *extra,
        home / rel,
        Path("/home/purin") / rel,
        Path("/home/pi") / rel,
    ]


def _install_epaper_path() -> Path | None:
    for cand in _epaper_lib_candidates():
        try:
            if cand.is_dir():
                lib_str = str(cand.resolve())
                if lib_str not in sys.path:
                    sys.path.insert(0, lib_str)
                logger.info("waveshare_epd: added to sys.path -> %s", lib_str)
                return cand.resolve()
        except OSError as e:
            logger.debug("Skip e-Paper candidate %s: %s", cand, e)
    logger.error(
        "waveshare_epd: no library directory found. Install Waveshare e-Paper code and set "
        "PURIN_EPAPER_LIB to the full path of .../python/lib (root's home is /root under systemd)."
    )
    return None


_EPAPER_LIB: Path | None = _install_epaper_path()


def _truthy_env(name: str, default: str = "1") -> bool:
    v = os.environ.get(name, default).strip().lower()
    return v not in ("0", "false", "no", "off", "")


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class Display:
    """Lazy-init panel driver with locking, ghosting mitigation, and safe SPI handling."""

    width: int
    height: int

    def __init__(self, rotate: int = 0, invert: bool = False, coordinate_twist_deg: int = 0) -> None:
        self._rotate = rotate % 360
        self._invert = bool(invert)
        t = int(coordinate_twist_deg) % 360
        self._twist_deg = t if t in (0, 90, 180, 270) else 0
        self._base_w: int | None = None
        self._base_h: int | None = None
        self.width = 0
        self.height = 0
        # RLock: clear() and other paths may call _ensure_hardware() while already holding the HW lock.
        self._lock = threading.RLock()
        self._epd: Any | None = None
        self._partial_count = 0
        self._epd_cls: Callable[[], Any] | None = None
        self._last_update_epoch: float | None = None
        self._warm_boot_done = False

    @property
    def last_update_epoch(self) -> float | None:
        return self._last_update_epoch

    @property
    def rotation_degrees(self) -> int:
        return self._rotate % 360

    @property
    def invert_bits(self) -> bool:
        return self._invert

    @property
    def coordinate_twist_degrees(self) -> int:
        return self._twist_deg % 360

    def set_coordinate_twist_degrees(self, degrees: int) -> None:
        v = int(degrees) % 360
        if v not in (0, 90, 180, 270):
            v = 0
        with self._lock:
            self._twist_deg = v

    def _recompute_logical_size(self) -> None:
        if self._base_w is None or self._base_h is None:
            return
        w, h = self._base_w, self._base_h
        if self._rotate in (90, 270):
            w, h = h, w
        self.width, self.height = w, h

    def set_rotation(self, degrees: int) -> None:
        """Update rotation and logical width/height (thread-safe)."""
        v = int(degrees) % 360
        if v not in (0, 90, 180, 270):
            v = 0
        with self._lock:
            self._rotate = v
            self._recompute_logical_size()

    def set_invert(self, invert: bool) -> None:
        with self._lock:
            self._invert = bool(invert)

    def _load_driver_class(self) -> Callable[[], Any]:
        if self._epd_cls is not None:
            return self._epd_cls
        try:
            mod = importlib.import_module(f"waveshare_epd.{PANEL_MODULE}")
        except ImportError as e:
            logger.error("Cannot import waveshare_epd.%s: %s", PANEL_MODULE, e)
            raise
        epd_cls = getattr(mod, "EPD", None)
        if epd_cls is None:
            raise RuntimeError(f"waveshare_epd.{PANEL_MODULE} has no EPD class")
        self._epd_cls = epd_cls
        return epd_cls

    def probe_size(self) -> tuple[int, int]:
        """Ensure the driver is loaded and return logical width/height."""
        self._ensure_hardware()
        return self.width, self.height

    def _ensure_hardware(self) -> Any:
        if self._epd is not None:
            return self._epd
        with self._lock:
            if self._epd is not None:
                return self._epd
            cls = self._load_driver_class()
            epd = cls()
            bw = int(getattr(epd, "width", getattr(epd, "WIDTH", 0)))
            bh = int(getattr(epd, "height", getattr(epd, "HEIGHT", 0)))
            self._base_w = bw
            self._base_h = bh
            w, h = bw, bh
            if self._rotate in (90, 270):
                w, h = h, w
            self.width, self.height = w, h
            self._epd = epd
            logger.info("EPD initialized module=%s size=%sx%s", PANEL_MODULE, w, h)
        return self._epd

    def _maybe_full_clean(self, epd: Any) -> None:
        if self._partial_count < 10:
            return
        try:
            epd.init()
            epd.Clear(0xFF)
        except (IOError, OSError) as e:
            logger.warning("Full clean failed: %s", e)
        finally:
            self._partial_count = 0

    def _warm_boot_if_needed(self, epd: Any) -> None:
        """Matches common Waveshare bring-up: init → pause → full white → pause (legacy app style)."""
        if self._warm_boot_done:
            return
        delay = _float_env("PURIN_EPD_INIT_SLEEP_SEC", 0.0)
        try:
            epd.init()
            if delay > 0:
                time.sleep(delay)
            epd.Clear(0xFF)
            if delay > 0:
                time.sleep(delay)
        except (IOError, OSError) as e:
            logger.warning("EPD warm boot failed: %s", e)
            return
        self._warm_boot_done = True
        logger.info(
            "EPD warm boot done (module=%s) — matched Waveshare flow: init → Clear(0xFF)",
            PANEL_MODULE,
        )

    @staticmethod
    def _panel_variants(base: Image.Image, target_w: int, target_h: int) -> list[Image.Image]:
        """When the frame is not already panel-sized, try 0°/90°/270° like the working ink stack."""
        im = base.convert("1")
        if im.size == (target_w, target_h):
            return [im]
        return [
            im,
            im.rotate(90, expand=True, fillcolor=255),
            im.rotate(270, expand=True, fillcolor=255),
        ]

    def _push_frame(self, epd: Any, image: Image.Image) -> bool:
        """Send a 1-bit frame; return True if display() succeeded."""
        buf_fn = getattr(epd, "getbuffer", None)
        tw, th = self.width, self.height
        variants = self._panel_variants(image, tw, th)
        last_err: OSError | IOError | None = None
        for cand in variants:
            try:
                frame = cand.convert("1")
                if frame.size != (tw, th):
                    frame = frame.resize((tw, th), Image.Resampling.LANCZOS).convert("1")
                if not callable(buf_fn):
                    logger.error("EPD driver has no getbuffer(); cannot push frame")
                    return False
                buf = buf_fn(frame)
                epd.display(buf)
                logger.info(
                    "EPD pushed frame %sx%s (%d bytes RAM) variant=%sx%s→%sx%s module=%s",
                    tw,
                    th,
                    len(buf) if hasattr(buf, "__len__") else -1,
                    cand.size[0],
                    cand.size[1],
                    tw,
                    th,
                    PANEL_MODULE,
                )
                return True
            except (IOError, OSError) as e:
                last_err = e
                logger.debug("EPD variant push failed (%sx%s→%sx%s): %s", cand.size[0], cand.size[1], tw, th, e)
        if last_err is not None:
            logger.warning("EPD refresh failed (exhausted rotations): %s", last_err)
        return False

    def _sleep_panel(self, epd: Any) -> None:
        # Waveshare's stock demo does NOT call epd.sleep() between frames; sleep() runs module_exit().
        if not _truthy_env("PURIN_EPD_SLEEP_AFTER_DRAW", "0"):
            return
        try:
            epd.sleep()
        except (IOError, OSError) as e:
            logger.warning("EPD sleep failed: %s", e)

    def _draw_to_panel(self, image: Image.Image) -> None:
        logger.info(
            "EPD _draw_to_panel: PIL size=%sx%s mode=%s logical=%sx%s",
            image.size[0],
            image.size[1],
            image.mode,
            getattr(self, "width", "?"),
            getattr(self, "height", "?"),
        )
        epd = self._ensure_hardware()
        logger.info("EPD: driver instance ready (module=%s)", PANEL_MODULE)

        def run() -> None:
            ok = False
            logger.info(
                "EPD: waiting for hardware mutex (thread=%s)",
                threading.current_thread().name,
            )
            with self._lock:
                cur = image.convert("1")
                if self._invert:
                    cur = ImageOps.invert(cur)
                logger.info("EPD: mutex acquired — refresh begins")
                try:
                    logger.info("EPD: maybe_full_clean check (partial_count=%s)", self._partial_count)
                    self._maybe_full_clean(epd)
                    logger.info("EPD: warm_boot_if_needed …")
                    self._warm_boot_if_needed(epd)
                    logger.info(
                        "EPD: calling driver init() — if logs stop here, BUSY/SPI is stuck (see README)"
                    )
                    epd.init()
                    logger.info("EPD: init() returned OK")
                    logger.info("EPD: push_frame …")
                    ok = self._push_frame(epd, cur)
                except (IOError, OSError) as e:
                    logger.warning("EPD refresh failed: %s", e)
                    ok = False
                finally:
                    if ok:
                        self._sleep_panel(epd)
                if ok:
                    self._partial_count += 1
                    self._last_update_epoch = time.time()
                logger.info("EPD: refresh path exit ok=%s", ok)

        run()

    def clear(self) -> None:
        logger.info(
            "EPD clear: waiting for hardware mutex (thread=%s)",
            threading.current_thread().name,
        )
        with self._lock:
            logger.info("EPD clear: mutex acquired")
            try:
                epd = self._ensure_hardware()
                self._warm_boot_if_needed(epd)
                logger.info("EPD clear: calling init()")
                epd.init()
                logger.info("EPD clear: init() returned; calling Clear(0xFF)")
                epd.Clear(0xFF)
            except (IOError, OSError) as e:
                logger.warning("EPD clear failed: %s", e)
                return
            logger.info("EPD clear complete Clear(0xFF) module=%s", PANEL_MODULE)
            self._partial_count = 0
            self._last_update_epoch = time.time()

    def show_image(self, img: Image.Image) -> None:
        if self._twist_deg:
            img = img.rotate(-self._twist_deg, expand=True, fillcolor=255)
        if self._rotate:
            img = img.rotate(-self._rotate, expand=True, fillcolor=255)
        self._draw_to_panel(img)

    def show_text(self, text: str, font_size: int | None = None) -> None:
        self._ensure_hardware()
        profile = TextLayoutProfile.from_dict(effective_text_layout_dict())
        img = render_plaintext(text, self.width, self.height, profile, font_size=font_size)
        self.show_image(img)

    def shutdown(self) -> None:
        with self._lock:
            if self._epd is None:
                return
            try:
                self._epd.sleep()
            except (IOError, OSError) as e:
                logger.warning("EPD shutdown sleep failed: %s", e)


_singleton: Display | None = None
_singleton_lock = threading.Lock()


def get_display() -> Display:
    """Process-wide display instance (panel ownership lives here)."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            rot = effective_rotate()
            inv = effective_invert()
            twist = effective_coordinate_twist_deg()
            _singleton = Display(rotate=rot, invert=inv, coordinate_twist_deg=twist)
            logger.info(
                "EPD singleton: rotate=%s twist=%s invert=%s (data/display_settings.json)",
                rot,
                twist,
                inv,
            )
        return _singleton
