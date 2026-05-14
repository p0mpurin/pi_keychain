"""Flask entrypoint for the Purin Pi dashboard."""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

from flask import Flask, redirect, request

from app.epd import get_display
from app.routes import captive, dashboard


def _configure_logging() -> None:
    raw = os.environ.get("PURIN_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, raw, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    # By default hide per-request werkzeug spam so hardware logs stay visible.
    if os.environ.get("PURIN_LOG_HTTP", "").strip().lower() in ("1", "true", "yes", "on"):
        logging.getLogger("werkzeug").setLevel(logging.INFO)
    else:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)


def create_app() -> Flask:
    _configure_logging()
    here = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(here / "templates"),
        static_folder=str(here / "static"),
    )
    app.secret_key = os.environ.get("PURIN_SECRET_KEY", "change-me-on-device")

    app.register_blueprint(captive.bp)
    app.register_blueprint(dashboard.bp)

    @app.before_request
    def captive_redirect_foreign_host() -> object | None:
        host = request.host.split(":")[0].lower()
        allowed = {"10.42.0.1", "localhost", "127.0.0.1"}
        raw_extra = os.environ.get("PURIN_ALLOWED_HOSTS", "")
        allowed.update(h.strip().lower() for h in raw_extra.split(",") if h.strip())
        if host not in allowed:
            return redirect("http://10.42.0.1/", code=302)
        return None

    return app


def main() -> None:
    app = create_app()

    def handle_term(signum: int, frame: object | None) -> None:
        logging.info("Received signal %s; parking display then exiting", signum)
        try:
            disp = get_display()
            disp.show_text("Safe to unplug")
            disp.shutdown()
        except Exception:
            logging.exception("Safe shutdown display handler failed")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)

    host = os.environ.get("PURIN_BIND", "0.0.0.0")
    port = int(os.environ.get("PURIN_PORT", "80"))
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
