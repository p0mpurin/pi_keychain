"""Captive-portal probe endpoints — redirect phones to the dashboard."""

from __future__ import annotations

from flask import Blueprint, redirect

_CAPTIVE_HOME = "http://10.42.0.1/"

bp = Blueprint("captive", __name__)


def _redirect_home():
    return redirect(_CAPTIVE_HOME, code=302)


@bp.route("/generate_204")
@bp.route("/gen_204")
def android_generate_204():
    return _redirect_home()


@bp.route("/hotspot-detect.html")
def ios_hotspot_detect():
    return _redirect_home()


@bp.route("/library/test/success.html")
def ios_legacy_success():
    return _redirect_home()


@bp.route("/ncsi.txt")
def windows_ncsi():
    return _redirect_home()


@bp.route("/connecttest.txt")
def windows_connecttest():
    return _redirect_home()
