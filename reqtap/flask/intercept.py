"""Request-lifecycle capture for Flask.

Three hooks, one record. ``before_request`` starts a :class:`CapturedRequest`
and stashes it on ``flask.g``; ``after_request`` fills in the response;
``teardown_request`` adds a traceback if the handler raised and commits the
record to the store. ``teardown_request`` always runs (even on error), so it's
the reliable place to finalize — ``after_request`` is skipped when a request
raises.
"""

import time
import traceback as traceback_module
from collections.abc import Iterable

from flask import Flask, Response, g, request

from reqtap.core.models import CapturedRequest, truncate_text
from reqtap.core.store import RingBufferStore

#: reqtap never captures its own dashboard/API traffic.
DASHBOARD_PREFIX = "/_reqtap"

#: Placeholder shown instead of a redacted header value.
REDACTED = "<redacted>"

# Keys used to stash per-request state on ``flask.g``.
_RECORD_KEY = "_reqtap_record"
_START_KEY = "_reqtap_perf_start"


def install(
    app: Flask,
    *,
    store: RingBufferStore,
    max_body_bytes: int,
    redact_headers: set[str],
) -> None:
    """Register the three capture hooks on ``app``.

    Config is captured in this closure rather than read from a global, so the
    hooks stay pure functions of the request plus this fixed configuration.
    """

    @app.before_request
    def _begin() -> None:
        if request.path.startswith(DASHBOARD_PREFIX):
            return

        body, truncated = _capture_request_body(max_body_bytes)
        record = CapturedRequest(
            timestamp=time.time(),
            method=request.method,
            path=request.path,
            query_string=request.query_string.decode("utf-8", errors="replace"),
            remote_addr=request.remote_addr,
            request_headers=_redact(request.headers.items(), redact_headers),
            request_body=body,
            request_body_truncated=truncated,
        )
        setattr(g, _RECORD_KEY, record)
        setattr(g, _START_KEY, time.perf_counter())

    @app.after_request
    def _complete(response: Response) -> Response:
        record = getattr(g, _RECORD_KEY, None)
        if record is None:
            return response

        record.status = response.status_code
        record.response_headers = _redact(response.headers.items(), redact_headers)
        body, truncated = _capture_response_body(response, max_body_bytes)
        record.response_body = body
        record.response_body_truncated = truncated
        record.duration_ms = _elapsed_ms()
        return response

    @app.teardown_request
    def _finalize(exc: BaseException | None) -> None:
        record = getattr(g, _RECORD_KEY, None)
        if record is None:
            return

        if exc is not None:
            record.traceback = "".join(
                traceback_module.format_exception(type(exc), exc, exc.__traceback__)
            )
            # after_request was skipped because the request raised, so fill in
            # what it would have set.
            if record.status is None:
                record.status = 500
            if record.duration_ms is None:
                record.duration_ms = _elapsed_ms()

        store.add(record)


def _capture_request_body(max_body_bytes: int) -> tuple[str, bool]:
    """Capture the request body, truncated to ``max_body_bytes`` for storage.

    Multipart uploads are skipped rather than buffered — reading a file upload
    into memory just to capture it is exactly the overhead reqtap must avoid.
    Everything else is read (cached so the view can still use it) and truncated.
    """
    if (request.content_type or "").startswith("multipart/form-data"):
        return "<skipped: multipart upload>", False

    raw = request.get_data(cache=True)
    text = raw.decode("utf-8", errors="replace")
    return truncate_text(text, max_body_bytes)


def _capture_response_body(response: Response, max_body_bytes: int) -> tuple[str, bool]:
    """Capture the response body, skipping streamed/file responses.

    ``direct_passthrough`` responses (e.g. ``send_file``) must not be read here
    — doing so would consume the stream the real client needs.
    """
    if response.direct_passthrough:
        return "<skipped: streamed response>", False

    text = response.get_data(as_text=True)
    return truncate_text(text, max_body_bytes)


def _redact(
    header_items: Iterable[tuple[str, str]], redact_headers: set[str]
) -> dict[str, str]:
    """Copy header (name, value) pairs to a plain dict, masking redacted names."""
    return {
        key: (REDACTED if key.lower() in redact_headers else value)
        for key, value in header_items
    }


def _elapsed_ms() -> float:
    """Milliseconds since this request's perf-counter start."""
    start: float = getattr(g, _START_KEY, time.perf_counter())
    return (time.perf_counter() - start) * 1000
