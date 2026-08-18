"""Tests for the loopback gate on the dashboard.

This check is the only thing keeping captured bodies, headers and tracebacks
away from other machines. It restricts viewing, never capture.
"""

from typing import Any

import pytest
from flask import Flask, jsonify

from reqtap import ReqTap
from reqtap.flask.dashboard import _is_loopback_address

REMOTE_CLIENT = {"REMOTE_ADDR": "203.0.113.9"}


def build_app(**reqtap_kwargs: Any) -> tuple[Flask, ReqTap]:
    """An app with one endpoint and reqtap mounted."""
    app = Flask(__name__)

    @app.post("/login")
    def login() -> Any:
        return jsonify(ok=True)

    tap = ReqTap(app, live_reqtap_requests=True, **reqtap_kwargs)
    return app, tap


@pytest.mark.parametrize(
    ("address", "is_local"),
    [
        ("127.0.0.1", True),
        ("192.168.1.5", False),
        # The mapped form and the two guards are ours; the /8 maths is stdlib's.
        ("::ffff:127.0.0.1", True),
        ("::ffff:192.168.1.5", False),
        (None, False),
        ("localhost", False),
    ],
)
def test_loopback_check(address: str | None, is_local: bool) -> None:
    assert _is_loopback_address(address) is is_local


def test_gate_allows_local_and_refuses_remote() -> None:
    """Wiring test: deleting the before_request hook leaves the unit test green.

    One route is enough — the hook is registered on the blueprint, so it covers
    every route including ones added later.
    """
    app, _ = build_app()
    client = app.test_client()

    assert client.get("/_reqtap/api/requests").status_code == 200
    assert client.get("/_reqtap/api/requests", environ_overrides=REMOTE_CLIENT).status_code == 403


def test_short_prefix_mirrors_the_long_one() -> None:
    """``/_rq`` is a shorter alias for the same dashboard, not a separate one."""
    app, _ = build_app()
    client = app.test_client()

    assert client.get("/_rq/api/requests").status_code == 200
    assert client.get("/_rq/api/requests", environ_overrides=REMOTE_CLIENT).status_code == 403


def test_remote_traffic_is_still_captured() -> None:
    """The gate restricts viewing, not recording: traffic from anywhere is kept."""
    app, tap = build_app()
    app.test_client().post("/login", json={"password": "hunter2"}, environ_overrides=REMOTE_CLIENT)

    assert tap.store is not None
    record = tap.store.list()[0]
    assert record.path == "/login"
    assert "hunter2" in record.request_body
    # The client address is deliberately not stored; the gate reads it live.
    assert not hasattr(record, "remote_addr")
