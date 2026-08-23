"""Tests for the loopback gate on the dashboard.

This check is the only thing keeping captured bodies, headers and tracebacks
away from other machines. It restricts viewing, never capture.
"""

from typing import Any

import pytest
from flask import Flask, jsonify

from reqtap import ReqTap
from reqtap.core.constants import (
    REQTAP_USER_FACING_MSG_BODY_NOT_READ,
)
from reqtap.flask.dashboard import _is_loopback_address

# A documentation-only address that is reliably not loopback.
REMOTE_CLIENT = {"REMOTE_ADDR": "203.0.113.9"}


def build_app(**reqtap_kwargs: Any) -> tuple[Flask, ReqTap]:
    """An app with one endpoint and reqtap mounted."""
    app = Flask(__name__)

    @app.post("/login")
    def login() -> Any:
        return jsonify(ok=True)

    rqtap = ReqTap(app, live_reqtap_requests=True, **reqtap_kwargs)
    return app, rqtap


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
    app, rqtap = build_app()
    app.test_client().post("/login", json={"password": "hunter2"}, environ_overrides=REMOTE_CLIENT)

    assert rqtap.store is not None
    record = rqtap.store.list()[0]
    assert record.path == "/login"
    assert record.status == 200
    # Handler never reads the body, so reqtap does not have it.
    assert record.request_body == REQTAP_USER_FACING_MSG_BODY_NOT_READ
    assert not hasattr(record, "remote_addr")


# Host values a browser could send, and whether the dashboard should answer.
# A rebinding attack lands here: the connection is genuinely from 127.0.0.1,
# only the name in the Host header gives the attacker away.
HOST_CASES = [
    ("localhost", True),
    ("localhost:5000", True),
    ("LOCALHOST", True),  # Host is case-insensitive.
    ("localhost.", True),  # A trailing dot is the same name.
    ("myapp.localhost", True),  # RFC 6761: *.localhost resolves to loopback.
    ("127.0.0.1", True),
    ("127.0.0.1:5000", True),
    ("127.0.0.2", True),  # All of 127.0.0.0/8 is loopback.
    ("[::1]", True),
    ("[::1]:5000", True),
    ("[0:0:0:0:0:0:0:1]:5000", True),  # Same address, written out in full.
    ("[::ffff:127.0.0.1]", True),
    ("evil.com", False),
    ("localhost.evil.com", False),  # Ends with the attacker's name, not ours.
    ("evil.localhost.com", False),
    ("127.0.0.1.evil.com", False),
    ("192.168.1.5", False),
    ("[::1", False),  # Malformed bracket: urlsplit raises, we refuse.
]


@pytest.mark.parametrize(("host", "allowed"), HOST_CASES)
@pytest.mark.parametrize("prefix", ["/_reqtap", "/_rq"])
def test_host_header_gate(host: str, allowed: bool, prefix: str) -> None:
    """Both prefixes share one blueprint, so both must enforce the same rule."""
    app, _ = build_app()
    response = app.test_client().get(f"{prefix}/api/requests", headers={"Host": host})

    assert response.status_code == (200 if allowed else 403)


def test_missing_host_is_refused() -> None:
    """No Host at all is not a local request; refuse rather than guess."""
    app, _ = build_app()
    environ = {"HTTP_HOST": "", "SERVER_NAME": "", "SERVER_PORT": ""}
    response = app.test_client().get("/_reqtap/api/requests", environ_overrides=environ)

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("headers", "allowed"),
    [
        ({}, True),
        ({"Sec-Fetch-Site": "none"}, True),  # Typed into the address bar.
        ({"Sec-Fetch-Site": "same-origin"}, True),  # From the dashboard itself.
        ({"Sec-Fetch-Site": "cross-site"}, False),
        ({"Sec-Fetch-Site": "same-site"}, False),
        ({"Origin": "https://evil.com"}, False),
    ],
)
def test_cross_site_requests_are_refused(headers: dict[str, str], allowed: bool) -> None:
    """A correct Host is not enough when the host app turns CORS on.

    With flask-cors installed on the host app, a request from an attacker's page
    that carries the right Host would come back with the attacker's origin
    allowed, letting them read the buffer. Browsers mark those requests with
    Origin / Sec-Fetch-Site, and the dashboard has no use for either.
    """
    app, _ = build_app()
    response = app.test_client().get("/_reqtap/api/requests", headers=headers)

    assert response.status_code == (200 if allowed else 403)


def test_clickjacking_is_blocked() -> None:
    """No page may frame the dashboard and read it through the user's browser."""
    app, _ = build_app()
    response = app.test_client().get("/_reqtap/api/requests")

    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_known_gap_behind_a_trusted_proxy() -> None:
    """Documents issue #57, which this change does NOT fix.

    ProxyFix tells Flask to believe X-Forwarded-For and X-Forwarded-Host. Both
    values the gate reads then come from the caller, so a remote client can
    hand itself a pass. The gate only holds when nothing untrusted sits in
    front of the app.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix

    app, _ = build_app()
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_host=1)  # type: ignore[method-assign]

    forged = {"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "localhost"}
    response = app.test_client().get(
        "/_reqtap/api/requests", headers=forged, environ_overrides=REMOTE_CLIENT
    )

    # Not the behaviour we want, just the behaviour we have. See issue #57.
    assert response.status_code == 200
