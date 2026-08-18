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
from reqtap.core.constants import REQTAP_CONTENT_FACING_MESSAGE_REDACTED
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
    assert record.query_string == "bridge_colour=<redacted by reqtap>"
    assert record.status == 200
    assert record.duration_ms is not None and record.duration_ms >= 0
    assert "Bridge Colour: red" in record.response_body


def test_timing_covers_request_and_response_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Flask(__name__)
    clock = 0.0
    events: list[str] = []
    # Held before patching: the wrappers below replace these module attributes,
    # so calling them by name from inside a wrapper would recurse.
    real_capture_request_body = intercept._capture_request_body
    real_capture_response_body = intercept._capture_response_body

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
        return real_capture_request_body(body_preview_bytes)

    def capture_response_body(response: Response, body_preview_bytes: int) -> tuple[str, bool]:
        nonlocal clock
        events.append("response body")
        clock += 0.03
        return real_capture_response_body(response, body_preview_bytes)

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
    assert ("Authorization", REQTAP_CONTENT_FACING_MESSAGE_REDACTED) in record.request_headers
    assert "secret-token" not in str(record.request_headers)


def test_repeated_headers_are_all_captured() -> None:
    """Every repeated name must survive; Set-Cookie is the one that carries secrets."""
    app, tap = build_app()

    @app.get("/multi")
    def multi() -> Response:
        response = Response("ok")
        for name in ("first", "second", "third"):
            response.headers.add("Set-Cookie", f"{name}=x; Path=/")
        return response

    app.test_client().get("/multi")

    record = tap.store.list()[0]
    cookies = [value for name, value in record.response_headers if name == "Set-Cookie"]
    assert len(cookies) == 3


def test_response_cookies_are_redacted() -> None:
    """Set-Cookie carries the session being issued, so it must not be stored raw."""
    app, tap = build_app()

    @app.get("/login")
    def login() -> Response:
        response = Response("ok")
        response.set_cookie("session", "secret-token")
        return response

    app.test_client().get("/login")

    record = tap.store.list()[0]
    assert "secret-token" not in str(record.response_headers)


def test_large_body_is_truncated() -> None:
    app, tap = build_app(body_preview_bytes=10)
    app.test_client().post("/echo", data="x" * 1000, content_type="application/json")

    record = tap.store.list()[0]
    assert record.request_body_truncated is True
    assert len(record.request_body.encode("utf-8")) <= 10


def test_query_values_are_redacted_but_keys_are_kept() -> None:
    """A reset token in the query string must not land in the buffer."""
    app, tap = build_app()
    app.test_client().get("/bridge?token=sk_live_9&page=2")

    record = tap.store.list()[0]
    assert record.query_string == (
        "token=<redacted by reqtap>&page=<redacted by reqtap>"
    )
    assert "sk_live_9" not in record.query_string


@pytest.mark.parametrize(
    ("query_string", "expected"),
    [
        ("", ""),
        ("flag", "flag"),
        ("a=1&a=2", "a=<redacted by reqtap>&a=<redacted by reqtap>"),
        ("empty=", "empty=<redacted by reqtap>"),
    ],
)
def test_query_redaction_edge_cases(query_string: str, expected: str) -> None:
    """Bare keys, repeats, and empty values keep their shape."""
    app, tap = build_app()
    app.test_client().get(f"/bridge?{query_string}" if query_string else "/bridge")

    assert tap.store.list()[0].query_string == expected


def test_client_address_is_not_stored() -> None:
    """Personal data with little debugging value: not captured at all."""
    app, tap = build_app()
    app.test_client().get("/bridge", environ_overrides={"REMOTE_ADDR": "203.0.113.9"})

    record = tap.store.list()[0]
    assert not hasattr(record, "remote_addr")
    assert "203.0.113.9" not in str(record.to_dict())


@pytest.mark.parametrize(
    "path",
    ["/_reqtap", "/_reqtap/anything", "/_rq", "/_rq/anything"],
)
def test_dashboard_traffic_is_not_captured(path: str) -> None:
    app, tap = build_app()
    # Status doesn't matter: the skip is based on the reserved route namespace.
    app.test_client().get(path)
    assert tap.store.list() == []


@pytest.mark.parametrize("path", ["/_reqtapping", "/_reqtapanything", "/_rquest"])
def test_paths_similar_to_dashboard_routes_are_captured(path: str) -> None:
    app, tap = build_app()

    response = app.test_client().post(path)

    record = tap.store.list()[0]
    assert record.method == "POST"
    assert record.path == path
    assert record.status == response.status_code


def test_app_factory_keeps_one_store_per_app() -> None:
    """One extension, two apps: each keeps its own buffer instead of the last one winning."""
    tap = ReqTap(live_reqtap_requests=True)
    first, second = Flask("first"), Flask("second")

    for app in (first, second):

        @app.get("/ping")
        def ping() -> str:
            return "ok"

        tap.init_app(app)

    first.test_client().get("/ping")

    assert len(first.extensions["reqtap"].list()) == 1
    assert second.extensions["reqtap"].list() == []
    # tap.store cannot guess which app is meant outside a request.
    with pytest.raises(RuntimeError, match="several apps"):
        _ = tap.store
    with second.app_context():
        assert tap.store is second.extensions["reqtap"]


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
    assert "reqtap is ACTIVE" in caplog.text
    warning = next(record for record in caplog.records if record.levelname == "WARNING")
    assert "REQTAP WARNING" in warning.getMessage()
    assert warning.getMessage().count("!") >= 20


def test_silent_when_inactive(caplog: pytest.LogCaptureFixture) -> None:
    # The safe default state says nothing at all.
    with caplog.at_level(logging.WARNING, logger="reqtap"):
        ReqTap(Flask(__name__))
    assert caplog.records == []


# Request capture must stay out of the way of every supported body-reading path.


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
    # Exercise framework-cached readers separately from direct stream access.
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
