"""Tests for response bodies the interceptor cannot treat as text.

An unreadable body must degrade to "not recorded", never to a failed request.
"""

import io
from typing import Any

import pytest
from flask import Flask, Response, send_file

from reqtap import ReqTap
from reqtap.flask import intercept

# First bytes of every PNG. 0x89 is deliberately not valid UTF-8.
PNG_SIGNATURE = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])


def build_app(**reqtap_kwargs: Any) -> tuple[Flask, ReqTap]:
    """An app whose endpoints return bodies the capture layer finds awkward."""
    app = Flask(__name__)

    @app.get("/png")
    def png() -> Response:
        return Response(PNG_SIGNATURE, mimetype="image/png")

    @app.get("/latin1")
    def latin1() -> Response:
        # Labelled text, but 0xe9 is invalid UTF-8: content type is not the test.
        return Response("café".encode("latin-1"), mimetype="text/plain")

    @app.get("/download")
    def download() -> Response:
        return send_file(io.BytesIO(b"filebytes"), mimetype="application/octet-stream")

    @app.get("/text")
    def text() -> Response:
        return Response("plain and decodable", mimetype="text/plain")

    tap = ReqTap(app, live_reqtap_requests=True, **reqtap_kwargs)
    return app, tap


@pytest.mark.parametrize("path", ["/png", "/latin1"])
def test_binary_body_is_skipped_not_fatal(path: str) -> None:
    """An undecodable body reaches the client intact and records a sentinel.

    /latin1 is labelled text/plain: the bytes decide, not the content type.
    """
    app, tap = build_app()
    response = app.test_client().get(path)

    assert response.status_code == 200
    record = tap.store.list()[0]
    assert record.status == 200
    assert "skipped" in record.response_body


def test_send_file_body_is_not_consumed() -> None:
    """The existing direct_passthrough guard still holds."""
    app, tap = build_app()
    response = app.test_client().get("/download")

    assert response.data == b"filebytes"
    assert "skipped" in tap.store.list()[0].response_body


def run_streamed_endpoint(*, with_reqtap: bool) -> tuple[int, ReqTap | None]:
    """Serve a generator response; report how many chunks got pulled out of it."""
    chunks_yielded = 0

    app = Flask(__name__)

    @app.get("/stream")
    def stream() -> Response:
        def generate() -> Any:
            nonlocal chunks_yielded
            for index in range(10):
                chunks_yielded += 1
                yield f"chunk {index}\n"

        return Response(generate(), mimetype="text/event-stream")

    tap = ReqTap(app, live_reqtap_requests=True) if with_reqtap else None
    app.test_client().get("/stream")
    return chunks_yielded, tap


def test_generator_response_is_not_drained() -> None:
    """Capture must not pull chunks out of a streamed body.

    Measured against the same app without reqtap, not against zero: the WSGI
    layer pulls the first chunk itself to force ``start_response``.
    """
    baseline_chunks, _ = run_streamed_endpoint(with_reqtap=False)
    captured_chunks, tap = run_streamed_endpoint(with_reqtap=True)

    assert tap is not None
    assert captured_chunks == baseline_chunks, (
        f"capture pulled {captured_chunks - baseline_chunks} extra chunks from the stream"
    )
    assert "skipped" in tap.store.list()[0].response_body


def test_capture_failure_does_not_break_the_request(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Backstop for input we haven't thought of: recording is optional,
    serving the request is not."""

    def explode(*args: Any, **kwargs: Any) -> tuple[str, bool]:
        raise RuntimeError("simulated capture bug")

    monkeypatch.setattr(intercept, "_capture_response_body", explode)

    app, _ = build_app()
    response = app.test_client().get("/text")

    assert response.status_code == 200
    assert "simulated capture bug" in caplog.text
