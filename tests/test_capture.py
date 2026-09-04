"""Tests for end-to-end request capture through the Flask intercept hooks.

Each test wires reqtap into a tiny app, fires a request with the test client,
and inspects what landed in the store.
"""

import json
import logging
import time
from datetime import datetime
from io import BytesIO
from typing import Any, NoReturn
from urllib.parse import parse_qsl

import pytest
from flask import Flask, Response, jsonify, request

from reqtap import ReqTap
from reqtap.core.constants import (
    REQTAP_USER_FACING_MSG_BODY_CONSUMED,
    REQTAP_USER_FACING_MSG_BODY_NOT_READ,
    REQTAP_USER_FACING_MSG_BODY_REDACTION_FAILED,
    REQTAP_USER_FACING_MSG_MULTIPART,
    REQTAP_USER_FACING_MSG_REDACTED,
)
from reqtap.flask import intercept


def build_app(**reqtap_kwargs: Any) -> tuple[Flask, ReqTap]:
    """A 3-endpoint app with reqtap activated; returns (app, rqtap)."""
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

    rqtap = ReqTap(app, live_reqtap_requests=True, **reqtap_kwargs)
    return app, rqtap


def test_get_request_is_captured() -> None:
    app, rqtap = build_app()
    app.test_client().get("/bridge?bridge_colour=red")

    record = rqtap.store.list()[0]
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

    rqtap = ReqTap(app, live_reqtap_requests=True)
    app.test_client().post("/timed", data="payload")

    record = rqtap.store.list()[0]
    assert events.index("timestamp") < events.index("request body")
    assert events.index("timer") < events.index("request body")
    assert record.duration_ms == pytest.approx(60.0)


def test_post_body_is_captured_both_ways() -> None:
    app, rqtap = build_app()
    app.test_client().post("/echo", json={"item": "coffee"})

    record = rqtap.store.list()[0]
    assert record.method == "POST"
    assert record.status == 201
    assert "coffee" in record.request_body
    assert "coffee" in record.response_body


@pytest.mark.parametrize(
    "request_mimetype",
    ["application/json", "application/problem+json"],
)
def test_json_body_sensitive_values_are_redacted_both_ways(
    request_mimetype: str,
) -> None:
    app, rqtap = build_app()
    payload = {
        "email": "dev@example.com",
        "password": "hunter2",
        "profile": {"oauthToken": "nested-token"},
        "items": [{"client_secret": "deep-secret", "name": "coffee"}],
    }

    app.test_client().post(
        "/echo",
        data=json.dumps(payload),
        content_type=request_mimetype,
    )

    record = rqtap.store.list()[0]
    expected = {
        "email": "dev@example.com",
        "password": REQTAP_USER_FACING_MSG_REDACTED,
        "profile": {"oauthToken": REQTAP_USER_FACING_MSG_REDACTED},
        "items": [
            {
                "client_secret": REQTAP_USER_FACING_MSG_REDACTED,
                "name": "coffee",
            }
        ],
    }
    assert json.loads(record.request_body) == expected
    assert json.loads(record.response_body) == {"you_sent": expected}


def test_form_body_sensitive_values_are_redacted_both_ways() -> None:
    app = Flask(__name__)

    @app.post("/form")
    def form() -> Response:
        raw = request.get_data(cache=True)
        return Response(raw, mimetype="application/x-www-form-urlencoded")

    rqtap = ReqTap(app, live_reqtap_requests=True)
    app.test_client().post(
        "/form",
        data="username=alice&password=hunter2&api%5Fkey=sk_live_9",
        content_type="application/x-www-form-urlencoded",
    )

    record = rqtap.store.list()[0]
    for body in (record.request_body, record.response_body):
        assert dict(parse_qsl(body)) == {
            "username": "alice",
            "password": REQTAP_USER_FACING_MSG_REDACTED,
            "api_key": REQTAP_USER_FACING_MSG_REDACTED,
        }


def test_malformed_structured_bodies_fail_closed() -> None:
    app = Flask(__name__)

    @app.post("/malformed")
    def malformed() -> Response:
        request.get_data(cache=True)
        return Response(
            '{"token":"response-secret"',
            mimetype="application/json",
        )

    rqtap = ReqTap(app, live_reqtap_requests=True)
    app.test_client().post(
        "/malformed",
        data='{"password":"request-secret"',
        content_type="application/json",
    )

    record = rqtap.store.list()[0]
    assert record.request_body == REQTAP_USER_FACING_MSG_BODY_REDACTION_FAILED
    assert record.response_body == REQTAP_USER_FACING_MSG_BODY_REDACTION_FAILED
    assert "request-secret" not in record.request_body
    assert "response-secret" not in record.response_body


def test_error_captures_traceback_and_500() -> None:
    app, rqtap = build_app()
    app.test_client().get("/boom")

    record = rqtap.store.list()[0]
    assert record.status == 500
    assert record.traceback is not None
    assert "RuntimeError" in record.traceback
    assert "kaboom" in record.traceback


@pytest.mark.parametrize(
    "header_name",
    [
        "Authorization",
        "Api-Key",
        "X-API-Token",
        "X-Vendor-Secret",
        "X-OAuth-Code",
    ],
)
def test_sensitive_headers_are_redacted(header_name: str) -> None:
    app, rqtap = build_app()
    app.test_client().get("/hello", headers={header_name: "secret-value"})

    record = rqtap.store.list()[0]
    assert REQTAP_USER_FACING_MSG_REDACTED in dict(record.request_headers).values()
    assert "secret-value" not in str(record.request_headers)


@pytest.mark.parametrize("header_name", ["Author", "X-Coauthor", "X-Footpath"])
def test_ordinary_headers_are_not_redacted(header_name: str) -> None:
    app, rqtap = build_app()
    app.test_client().get("/hello", headers={header_name: "useful-value"})

    assert "useful-value" in dict(rqtap.store.list()[0].request_headers).values()


def test_custom_header_redaction_extends_automatic_patterns() -> None:
    app, rqtap = build_app(redact_headers=["X-Custom-Id"])
    app.test_client().get(
        "/hello",
        headers={"Authorization": "automatic-secret", "X-Custom-Id": "custom-secret"},
    )

    headers = dict(rqtap.store.list()[0].request_headers)
    assert headers["Authorization"] == REQTAP_USER_FACING_MSG_REDACTED
    assert headers["X-Custom-Id"] == REQTAP_USER_FACING_MSG_REDACTED


def test_repeated_headers_are_all_captured() -> None:
    """Every repeated name must survive; Set-Cookie is the one that carries secrets."""
    app, rqtap = build_app()

    @app.get("/multi")
    def multi() -> Response:
        response = Response("ok")
        for name in ("first", "second", "third"):
            response.headers.add("Set-Cookie", f"{name}=x; Path=/")
        return response

    app.test_client().get("/multi")

    record = rqtap.store.list()[0]
    cookies = [value for name, value in record.response_headers if name == "Set-Cookie"]
    assert len(cookies) == 3


def test_response_cookies_are_redacted() -> None:
    """Set-Cookie carries the session being issued, so it must not be stored raw."""
    app, rqtap = build_app()

    @app.get("/login")
    def login() -> Response:
        response = Response("ok")
        response.set_cookie("session", "secret-token")
        return response

    app.test_client().get("/login")

    record = rqtap.store.list()[0]
    assert "secret-token" not in str(record.response_headers)


def test_large_body_is_truncated() -> None:
    app, rqtap = build_app(body_preview_bytes=10)
    payload = {"password": "secret-value", "padding": "x" * 1000}
    app.test_client().post(
        "/echo",
        data=json.dumps(payload),
        content_type="application/json",
    )

    record = rqtap.store.list()[0]
    assert record.request_body_truncated is True
    assert record.response_body_truncated is True
    assert len(record.request_body.encode("utf-8")) <= 10
    assert len(record.response_body.encode("utf-8")) <= 10
    assert "secret-value" not in record.request_body
    assert "secret-value" not in record.response_body


def test_secret_query_values_are_redacted_and_ordinary_ones_are_kept() -> None:
    """A reset token must not land in the buffer; ordinary params stay readable."""
    app, rqtap = build_app()
    app.test_client().get("/bridge?token=sk_live_9&page=2")

    record = rqtap.store.list()[0]
    assert record.query_string == "token=<redacted by reqtap>&page=2"
    assert "sk_live_9" not in record.query_string


@pytest.mark.parametrize(
    ("query_string", "expected"),
    [
        # Patterns are substrings, so unlisted variants are still caught.
        ("reset_token=x", "reset_token=<redacted by reqtap>"),
        ("apiKey=x", "apiKey=<redacted by reqtap>"),
        ("X-Csrf=x", "X-Csrf=<redacted by reqtap>"),
        # Match the decoded key Flask gives the application, while preserving
        # its original spelling in the captured query string.
        ("to%6ben=x", "to%6ben=<redacted by reqtap>"),
        ("api%5Fkey=x", "api%5Fkey=<redacted by reqtap>"),
        # ...but narrow enough to leave ordinary words alone.
        ("author=josh", "author=josh"),
        ("auth=x", "auth=<redacted by reqtap>"),
        ("user_auth=x", "user_auth=<redacted by reqtap>"),
        # Short names are matched as whole words, so ordinary words that merely
        # contain them stay readable.
        ("coauthor=jane", "coauthor=jane"),
        ("oauth=x", "oauth=<redacted by reqtap>"),
        ("carbon_footprint=2", "carbon_footprint=2"),
        ("otp=123456", "otp=<redacted by reqtap>"),
        # A hump counts as a word break too, or "userAuth" would slip through.
        ("userAuth=x", "userAuth=<redacted by reqtap>"),
        ("otpCode=x", "otpCode=<redacted by reqtap>"),
        ("passenger=3", "passenger=3"),
        ("passphrase=s", "passphrase=<redacted by reqtap>"),
    ],
)
def test_query_key_matching(query_string: str, expected: str) -> None:
    """Which keys count as carrying a credential."""
    app, rqtap = build_app()
    app.test_client().get(f"/bridge?{query_string}")

    assert rqtap.store.list()[0].query_string == expected


@pytest.mark.parametrize(
    ("query_string", "expected"),
    [
        ("", ""),
        ("flag", "flag"),
        ("a=1&a=2", "a=1&a=2"),
        ("token=1&token=2", "token=<redacted by reqtap>&token=<redacted by reqtap>"),
        ("empty=", "empty="),
        ("token=", "token=<redacted by reqtap>"),
    ],
)
def test_query_redaction_edge_cases(query_string: str, expected: str) -> None:
    """Bare keys, repeats, and empty values keep their shape."""
    app, rqtap = build_app()
    app.test_client().get(f"/bridge?{query_string}" if query_string else "/bridge")

    assert rqtap.store.list()[0].query_string == expected


def test_client_address_is_not_stored() -> None:
    """Personal data with little debugging value: not captured at all."""
    app, rqtap = build_app()
    app.test_client().get("/bridge", environ_overrides={"REMOTE_ADDR": "203.0.113.9"})

    record = rqtap.store.list()[0]
    assert not hasattr(record, "remote_addr")
    assert "203.0.113.9" not in str(record.to_dict())


@pytest.mark.parametrize(
    "path",
    ["/_reqtap", "/_reqtap/anything", "/_rq", "/_rq/anything"],
)
def test_dashboard_traffic_is_not_captured(path: str) -> None:
    app, rqtap = build_app()
    # Status doesn't matter: the skip is based on the reserved route namespace.
    app.test_client().get(path)
    assert rqtap.store.list() == []


@pytest.mark.parametrize("path", ["/_reqtapping", "/_reqtapanything", "/_rquest"])
def test_paths_similar_to_dashboard_routes_are_captured(path: str) -> None:
    app, rqtap = build_app()

    response = app.test_client().post(path)

    record = rqtap.store.list()[0]
    assert record.method == "POST"
    assert record.path == path
    assert record.status == response.status_code


def test_app_factory_keeps_one_store_per_app() -> None:
    """One extension, two apps: each keeps its own buffer instead of the last one winning."""
    rqtap = ReqTap(live_reqtap_requests=True)
    first, second = Flask("first"), Flask("second")

    for app in (first, second):

        @app.get("/ping")
        def ping() -> str:
            return "ok"

        rqtap.init_app(app)

    first.test_client().get("/ping")

    assert len(first.extensions["reqtap"].list()) == 1
    assert second.extensions["reqtap"].list() == []
    # rqtap.store cannot guess which app is meant outside a request.
    with pytest.raises(RuntimeError, match="several apps"):
        _ = rqtap.store
    with second.app_context():
        assert rqtap.store is second.extensions["reqtap"]


def test_inactive_captures_nothing() -> None:
    app = Flask(__name__)

    @app.get("/x")
    def x() -> str:
        return "ok"

    rqtap = ReqTap(app)  # no flag → off
    assert rqtap.store is None
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

    rqtap = ReqTap(app, live_reqtap_requests=True)
    return app, rqtap


def test_handler_can_still_read_raw_stream() -> None:
    app, rqtap = build_body_reader_app(lambda: request.stream.read())
    response = app.test_client().post("/read", data=b"payload")

    assert response.get_data(as_text=True) == repr(b"payload")
    # Reading the stream directly leaves werkzeug nothing cached, and capture
    # runs after the handler, so the body is gone. Say so rather than show "".
    record = rqtap.store.list()[0]
    assert record.request_body == REQTAP_USER_FACING_MSG_BODY_CONSUMED
    assert record.request_body_total_bytes == 7


def test_request_with_no_body_records_an_empty_one() -> None:
    """No body sent means no body to report, not an unread one."""
    app = Flask(__name__)

    @app.get("/ping")
    def ping() -> str:
        return "ok"

    rqtap = ReqTap(app, live_reqtap_requests=True)
    app.test_client().get("/ping")

    assert rqtap.store.list()[0].request_body == ""


def test_unread_body_is_reported_not_fetched() -> None:
    """Reading here would wait on the client, so the stream must stay untouched."""
    app = Flask(__name__)

    @app.post("/guard")
    def guard() -> tuple[str, int]:
        return "denied", 401  # never touches the body

    @app.before_request
    def explode_if_read() -> None:
        def boom(*args: object, **kwargs: object) -> NoReturn:
            raise AssertionError("reqtap read the request stream")

        request.stream.read = boom  # type: ignore[method-assign]

    rqtap = ReqTap(app, live_reqtap_requests=True)
    response = app.test_client().post("/guard", data=b"secret-payload")

    record = rqtap.store.list()[0]
    assert response.status_code == 401
    assert record.request_body == REQTAP_USER_FACING_MSG_BODY_NOT_READ
    assert record.request_body_total_bytes == 14  # the header still tells us the size


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

    rqtap = ReqTap(app, live_reqtap_requests=True)
    response = app.test_client().post(
        "/upload", data={"f": (BytesIO(b"file-bytes"), "f.txt")}
    )

    assert response.get_data(as_text=True) == repr(b"file-bytes")
    assert rqtap.store.list()[0].request_body == REQTAP_USER_FACING_MSG_MULTIPART
