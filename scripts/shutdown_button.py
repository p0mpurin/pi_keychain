#!/usr/bin/env python3
"""Optional GPIO shutdown button — expects gpiozero on Raspberry Pi OS."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("shutdown_button")


def main() -> None:
    try:
        from gpiozero import Button  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("gpiozero not installed; exiting.")
        sys.exit(0)

    hold_seconds = float(os.environ.get("PURIN_SHUTDOWN_HOLD_S", "3"))
    gpio_pin = int(os.environ.get("PURIN_SHUTDOWN_GPIO", "3"))

    btn = Button(gpio_pin, pull_up=True, hold_time=hold_seconds)

    def shutdown() -> None:
        logger.info("GPIO hold detected — powering off.")
        subprocess.run(["/usr/bin/systemctl", "poweroff"], check=False)

    btn.when_held = shutdown
    logger.info("Listening on GPIO%s (hold %.1fs to power off)", gpio_pin, hold_seconds)

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
