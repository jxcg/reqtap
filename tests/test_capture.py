"""Tests for end-to-end request capture through the Flask intercept hooks.

Each test wires reqtap into a tiny app, fires a request with the test client,
and inspects what landed in the store.
"""

import logging
import time
from datetime import datetime
from io import BytesIO
from typing import Any, NoReturn

import pytest
from flask import Flask, Response, jsonify, request

from reqtap import ReqTap
from reqtap.flask import intercept


def build_app(**reqtap_kwargs: Any) -> tuple[Flask, ReqTap]:
    """A 3-endpoint app with reqtap activated; returns (app, tap)."""
    app = Flask(__name__)

    @app.get("/bridge")
    def place() -> Response:
        return jsonify(message=f"Bridge Colour: {request.args.get('bridge_colour', None)}!")

    @app.post("/echo")
    def echo() -> tuple[Response, int]:
        return jsonify(you_sent=request.get_json(silent=True) or {}), 201

    @app.get("/boom")
    def boom() -> NoReturn:
        raise RuntimeError("kaboom")

    tap = ReqTap(app, live_reqtap_requests=True, **reqtap_kwargs)
    return app, tap


def test_get_request_is_captured() -> None:
    app, tap = build_app()
    app.test_client().get("/bridge?bridge_colour=red")

    record = tap.store.list()[0]
    print(record)
    assert record.method == "GET"
    assert record.path == "/bridge"
    assert record.query_string == "bridge_colour=red"
    assert record.status == 200
    assert record.duration_ms is not None and record.duration_ms >= 0
    assert "Bridge Colour: red" in record.response_body


def test_timing_covers_request_and_response_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask(__name__)
    clock = 0.0
    events: list[str] = []
    original_capture_request_body = intercept._capture_request_body
    original_capture_response_body = intercept._capture_response_body

    class RecordingDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "RecordingDateTime":
            events.append("timestamp")
            return super().now(tz)

    def perf_counter() -> float:
        events.append("timer")
        return clock

    def capture_request_body(body_preview_bytes: int) -> tuple[str, bool]:
        nonlocal clock
        events.append("request body")
        clock += 0.01
        return original_capture_request_body(body_preview_bytes)

    def capture_response_body(response: Response, body_preview_bytes: int) -> tuple[str, bool]:
        nonlocal clock
        events.append("response body")
        clock += 0.03
        return original_capture_response_body(response, body_preview_bytes)

    monkeypatch.setattr(intercept, "datetime", RecordingDateTime)
    monkeypatch.setattr(time, "perf_counter", perf_counter)
    monkeypatch.setattr(intercept, "_capture_request_body", capture_request_body)
    monkeypatch.setattr(intercept, "_capture_response_body", capture_response_body)

    @app.post("/timed")
    def timed() -> str:
        nonlocal clock
        clock += 0.02
        return "ok"

    tap = ReqTap(app, live_reqtap_requests=True)
    app.test_client().post("/timed", data="payload")

    record = tap.store.list()[0]
    assert events.index("timestamp") < events.index("request body")
    assert events.index("timer") < events.index("request body")
    assert record.duration_ms == pytest.approx(60.0)


def test_post_body_is_captured_both_ways() -> None:
    app, tap = build_app()
    app.test_client().post("/echo", json={"item": "coffee"})

    record = tap.store.list()[0]
    assert record.method == "POST"
    assert record.status == 201
    assert "coffee" in record.request_body
    assert "coffee" in record.response_body


def test_error_captures_traceback_and_500() -> None:
    app, tap = build_app()
    app.test_client().get("/boom")

    record = tap.store.list()[0]
    assert record.status == 500
    assert record.traceback is not None
    assert "RuntimeError" in record.traceback
    assert "kaboom" in record.traceback


def test_sensitive_headers_are_redacted() -> None:
    app, tap = build_app()
    app.test_client().get("/hello", headers={"Authorization": "Bearer secret-token"})

    record = tap.store.list()[0]
    assert record.request_headers["Authorization"] == "<redacted>"
    assert "secret-token" not in str(record.request_headers)


def test_large_body_is_truncated() -> None:
    app, tap = build_app(body_preview_bytes=10)
    app.test_client().post("/echo", data="x" * 1000, content_type="application/json")

    record = tap.store.list()[0]
    assert record.request_body_truncated is True
    assert len(record.request_body.encode("utf-8")) <= 10


def test_dashboard_traffic_is_not_captured() -> None:
    app, tap = build_app()
    # Status doesn't matter: the skip is on the path prefix, not the outcome.
    app.test_client().get("/_reqtap/anything")
    assert tap.store.list() == []


def test_inactive_captures_nothing() -> None:
    app = Flask(__name__)

    @app.get("/x")
    def x() -> str:
        return "ok"

    tap = ReqTap(app)  # no flag → off
    assert tap.store is None
    assert app.test_client().get("/x").status_code == 200  # app still works


def test_warns_when_live(caplog: pytest.LogCaptureFixture) -> None:
    # Activation logs a WARNING (visible by default) so the user can't miss that
    # sensitive request data is being recorded.
    with caplog.at_level(logging.WARNING, logger="reqtap"):
        build_app()
    assert "reqtap is LIVE" in caplog.text
    assert any(record.levelname == "WARNING" for record in caplog.records)


def test_silent_when_inactive(caplog: pytest.LogCaptureFixture) -> None:
    # The safe default state says nothing at all.
    with caplog.at_level(logging.WARNING, logger="reqtap"):
        ReqTap(Flask(__name__))
    assert caplog.records == []


# Capture runs after the handler now, so these pin that reqtap stays out of the
# way of every way a handler can read the body.


def build_body_reader_app(read_body: Any) -> tuple[Flask, ReqTap]:
    """App whose single route reads the body via the supplied accessor."""
    app = Flask(__name__)

    @app.post("/read")
    def read() -> str:
        return repr(read_body())

    tap = ReqTap(app, live_reqtap_requests=True)
    return app, tap


def test_handler_can_still_read_raw_stream() -> None:
    app, tap = build_body_reader_app(lambda: request.stream.read())
    response = app.test_client().post("/read", data=b"payload")

    assert response.get_data(as_text=True) == repr(b"payload")
    # Reading the stream directly leaves werkzeug nothing cached, and capture
    # runs after the handler, so the body is gone. Say so rather than show "".
    record = tap.store.list()[0]
    assert record.request_body == "<skipped: body consumed by handler>"
    assert record.request_body_total_bytes == 7


def test_form_and_json_parsing_still_work() -> None:
    # Cached path, not request.stream — guard against a fix that breaks it.
    form_app, _ = build_body_reader_app(lambda: dict(request.form))
    assert form_app.test_client().post("/read", data={"a": "1"}).get_data(
        as_text=True
    ) == repr({"a": "1"})

    json_app, _ = build_body_reader_app(lambda: request.get_json())
    assert json_app.test_client().post("/read", json={"a": 1}).get_data(
        as_text=True
    ) == repr({"a": 1})


def test_multipart_upload_stream_is_untouched() -> None:
    # The multipart branch returns before reading, so files must still parse.
    app = Flask(__name__)

    @app.post("/upload")
    def upload() -> str:
        return repr(request.files["f"].read())

    tap = ReqTap(app, live_reqtap_requests=True)
    response = app.test_client().post(
        "/upload", data={"f": (BytesIO(b"file-bytes"), "f.txt")}
    )

    assert response.get_data(as_text=True) == repr(b"file-bytes")
    assert tap.store.list()[0].request_body == "<skipped: multipart upload>"
