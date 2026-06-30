"""Tests for end-to-end request capture through the Flask intercept hooks.

Each test wires reqtap into a tiny app, fires a request with the test client,
and inspects what landed in the store.
"""

import logging

from flask import Flask, jsonify, request

from reqtap import ReqTap


def build_app(**reqtap_kwargs):
    """A 3-endpoint app with reqtap activated; returns (app, tap)."""
    app = Flask(__name__)

    @app.get("/hello")
    def hello():
        return jsonify(message=f"Hello, {request.args.get('name', 'World')}!")

    @app.post("/echo")
    def echo():
        return jsonify(you_sent=request.get_json(silent=True) or {}), 201

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    tap = ReqTap(app, live_reqtap_requests=True, **reqtap_kwargs)
    return app, tap


def test_get_request_is_captured():
    app, tap = build_app()
    app.test_client().get("/hello?name=Josh")

    record = tap.store.list()[0]
    assert record.method == "GET"
    assert record.path == "/hello"
    assert record.query_string == "name=Josh"
    assert record.status == 200
    assert record.duration_ms is not None and record.duration_ms >= 0
    assert "Hello, Josh!" in record.response_body


def test_post_body_is_captured_both_ways():
    app, tap = build_app()
    app.test_client().post("/echo", json={"item": "coffee"})

    record = tap.store.list()[0]
    assert record.method == "POST"
    assert record.status == 201
    assert "coffee" in record.request_body
    assert "coffee" in record.response_body


def test_error_captures_traceback_and_500():
    app, tap = build_app()
    app.test_client().get("/boom")

    record = tap.store.list()[0]
    assert record.status == 500
    assert record.traceback is not None
    assert "RuntimeError" in record.traceback
    assert "kaboom" in record.traceback


def test_sensitive_headers_are_redacted():
    app, tap = build_app()
    app.test_client().get("/hello", headers={"Authorization": "Bearer secret-token"})

    record = tap.store.list()[0]
    assert record.request_headers["Authorization"] == "<redacted>"
    assert "secret-token" not in str(record.request_headers)


def test_large_body_is_truncated():
    app, tap = build_app(max_body_bytes=10)
    app.test_client().post("/echo", data="x" * 1000, content_type="application/json")

    record = tap.store.list()[0]
    assert record.request_body_truncated is True
    assert len(record.request_body.encode("utf-8")) <= 10


def test_dashboard_traffic_is_not_captured():
    app, tap = build_app()
    # 404s (no dashboard yet), but must be ignored regardless.
    app.test_client().get("/_reqtap/anything")
    assert tap.store.list() == []


def test_inactive_captures_nothing():
    app = Flask(__name__)

    @app.get("/x")
    def x():
        return "ok"

    tap = ReqTap(app)  # no flag → off
    assert tap.store is None
    assert app.test_client().get("/x").status_code == 200  # app still works


def test_warns_when_live(caplog):
    # Activation logs a WARNING (visible by default) so the user can't miss that
    # sensitive request data is being recorded.
    with caplog.at_level(logging.WARNING, logger="reqtap"):
        build_app()
    assert "reqtap is LIVE" in caplog.text
    assert any(record.levelname == "WARNING" for record in caplog.records)


def test_silent_when_inactive(caplog):
    # The safe default state says nothing at all.
    with caplog.at_level(logging.WARNING, logger="reqtap"):
        ReqTap(Flask(__name__))
    assert caplog.records == []
