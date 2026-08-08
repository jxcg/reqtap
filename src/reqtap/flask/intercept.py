"""Flask lifecycle hooks: start a record, fill response, commit to store.

``before_request`` starts it, ``after_request`` adds the response,
``teardown_request`` always runs and saves the record (even on errors).
"""

import time
import traceback as traceback_module
from collections.abc import Iterable
from datetime import UTC, datetime
from io import BytesIO

from flask import Flask, Response, g, request

from reqtap.core.models import CapturedRequest, truncate_text
from reqtap.core.store import RingBufferStore
from reqtap.flask.dashboard import DASHBOARD_PREFIX

# Placeholder shown instead of a redacted header value.
REDACTED = "<redacted>"

# Per-request scratch keys on flask.g.
_RECORD_KEY = "_reqtap_record"
_START_KEY = "_reqtap_perf_start"


def install(
    app: Flask,
    *,
    store: RingBufferStore,
    max_body_bytes: int,
    redact_headers: set[str],
) -> None:
    """Register capture hooks on ``app``. Called once at startup."""

    @app.before_request
    def _begin() -> None:
        """Grab request fields before the route handler runs."""
        if request.path.startswith(DASHBOARD_PREFIX):
            return

        body, truncated = _capture_request_body(max_body_bytes)
        now = datetime.now(UTC)
        record = CapturedRequest(
            # Same instant, two formats.
            timestamp=now.timestamp(),
            timestamp_utc=now.isoformat(),
            method=request.method,
            path=request.path,
            query_string=request.query_string.decode("utf-8", errors="replace"),
            remote_addr=request.remote_addr,
            request_headers=_redact(request.headers.items(), redact_headers),
            request_body=body,
            request_body_truncated=truncated,
        )
        # Stash on g so later hooks can find this record.
        setattr(g, _RECORD_KEY, record)
        setattr(g, _START_KEY, time.perf_counter())

    @app.after_request
    def _complete(response: Response) -> Response:
        """Fill in response fields after the handler returns."""
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
        """Save the record. Runs even when the handler raised."""
        record = getattr(g, _RECORD_KEY, None)
        if record is None:
            return

        if exc is not None:
            record.traceback = "".join(
                traceback_module.format_exception(type(exc), exc, exc.__traceback__)
            )
            # Handler raised, so after_request never ran. Patch in what we can.
            if record.status is None:
                record.status = 500
            if record.duration_ms is None:
                record.duration_ms = _elapsed_ms()

        store.add(record)


def _capture_request_body(max_body_bytes: int) -> tuple[str, bool]:
    """Read and truncate the request body.

    Skips multipart uploads (don't buffer files into memory for no reason).
    """
    if (request.content_type or "").startswith("multipart/form-data"):
        return "<skipped: multipart upload>", False

    raw = request.get_data(cache=True)
    # get_data() drains the one-shot WSGI body. Werkzeug's cache covers
    # get_data/form/json but not request.stream, so rewind it for raw readers.
    request.stream = BytesIO(raw)
    text = raw.decode("utf-8", errors="replace")
    return truncate_text(text, max_body_bytes)


def _capture_response_body(response: Response, max_body_bytes: int) -> tuple[str, bool]:
    """Read and truncate the response body.

    Skips streamed responses (send_file etc.) so we don't consume the stream.
    """
    if response.direct_passthrough:
        return "<skipped: streamed response>", False

    text = response.get_data(as_text=True)
    return truncate_text(text, max_body_bytes)


def _redact(
    header_items: Iterable[tuple[str, str]], redact_headers: set[str]
) -> dict[str, str]:
    """Copy headers to a dict, masking anything on the redact list."""
    return {
        key: (REDACTED if key.lower() in redact_headers else value)
        for key, value in header_items
    }


def _elapsed_ms() -> float:
    """How long this request took, in milliseconds."""
    start: float = getattr(g, _START_KEY, time.perf_counter())
    return (time.perf_counter() - start) * 1000
