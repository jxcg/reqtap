"""Flask lifecycle hooks: start a record, fill response, commit to store.

``before_request`` starts it, ``after_request`` adds the response,
``teardown_request`` always runs and saves the record (even on errors).
"""

import logging
import time
import traceback as traceback_module
from collections.abc import Iterable
from datetime import UTC, datetime

from flask import Flask, Response, g, request

from reqtap.core.constants import (
    DASHBOARD_PREFIX_LONG,
    DASHBOARD_PREFIX_SHORT,
    MAX_HEADER_CHARS,
    RECORD_KEY,
    REQTAP_USER_FACING_MSG_BODY_CONSUMED,
    REQTAP_USER_FACING_MSG_BODY_NOT_READ,
    REQTAP_USER_FACING_MSG_MULTIPART,
    REQTAP_USER_FACING_MSG_REDACTED,
    START_KEY,
)
from reqtap.core.models import CapturedRequest
from reqtap.core.redaction import (
    is_sensitive_key,
    redact_body_preview,
    redact_query_string,
)
from reqtap.core.store import RingBufferStore

logger = logging.getLogger("reqtap")

# Only ReqTap's own namespaces are skipped: the exact roots and anything below
# them. Matching on a bare prefix would also swallow app routes that merely
# start with the same characters, such as /_reqtapping or /_rquest.
_DASHBOARD_ROOTS = (DASHBOARD_PREFIX_LONG, DASHBOARD_PREFIX_SHORT)
_DASHBOARD_SUBPATHS = tuple(f"{root}/" for root in _DASHBOARD_ROOTS)


def install(
    app: Flask,
    *,
    store: RingBufferStore,
    body_preview_bytes: int,
    redact_headers: set[str],
) -> None:
    """Register capture hooks on ``app``. Called once at startup."""

    @app.before_request
    def _begin() -> None:
        """Grab request fields before the route handler runs."""
        if request.path in _DASHBOARD_ROOTS or request.path.startswith(_DASHBOARD_SUBPATHS):
            return

        try:
            now = datetime.now(UTC)
            start = time.perf_counter()
            # Body is captured in teardown, once the handler no longer needs it.
            record = CapturedRequest(
                # Same instant, two formats.
                timestamp=now.timestamp(),
                timestamp_utc=now.isoformat(),
                method=request.method,
                path=request.path,
                query_string=redact_query_string(
                    request.query_string.decode("utf-8", errors="replace")
                ),
                request_headers=_redact(request.headers.items(), redact_headers),
            )
        except Exception:
            # No record on g means the later hooks quietly do nothing.
            logger.warning("reqtap could not capture this request", exc_info=True)
            return

        # Stash on g so later hooks can find this record.
        setattr(g, RECORD_KEY, record)
        setattr(g, START_KEY, start)

    @app.after_request
    def _complete(response: Response) -> Response:
        """Fill in response fields after the handler returns.

        Sits in the response path of every request: failing to record must
        never become failing to serve.
        """
        record = getattr(g, RECORD_KEY, None)
        if record is None:
            return response

        try:
            record.status = response.status_code
            record.response_headers = _redact(response.headers.items(), redact_headers)
            body, truncated = _capture_response_body(response, body_preview_bytes)
            record.response_body = body
            record.response_body_truncated = truncated
            record.response_body_total_bytes = response.content_length
        except Exception:
            logger.warning("reqtap could not capture this response", exc_info=True)

        return response

    @app.teardown_request
    def _finalize(exc: BaseException | None) -> None:
        """Save the record. Runs even when the handler raised."""
        record = getattr(g, RECORD_KEY, None)
        if record is None:
            return

        # Own try: a body we cannot read must not cost us the whole record.
        try:
            record.request_body_total_bytes = request.content_length
            record.request_body, record.request_body_truncated = (
                _capture_request_body(body_preview_bytes)
            )
        except Exception:
            record.request_body = "<skipped: capture failed>"
            logger.warning("reqtap could not capture this request body", exc_info=True)

        try:
            # Last thing measured, so it covers both body captures symmetrically.
            record.duration_ms = _elapsed_ms()
            if exc is not None:
                record.traceback = "".join(
                    traceback_module.format_exception(type(exc), exc, exc.__traceback__)
                )
                # Handler raised, so after_request never ran. Patch in what we can.
                if record.status is None:
                    record.status = 500

            store.add(record)
        except Exception:
            logger.warning("reqtap could not store this record", exc_info=True)


def _capture_request_body(body_preview_bytes: int) -> tuple[str, bool]:
    """Preview the request body without reading more than we already have.

    Runs after the handler, so the body is either already in werkzeug's cache
    (free to reuse) or nobody read it (reported, never fetched: reading here
    would wait on bytes the client may never send).
    Skips multipart uploads (don't buffer files into memory for no reason).
    """
    if (request.content_type or "").startswith("multipart/form-data"):
        return REQTAP_USER_FACING_MSG_MULTIPART, False

    # get_data/form/json leave the body cached; reusing it costs nothing.
    cached = getattr(request, "_cached_data", None)
    if cached is not None:
        return redact_body_preview(cached, request.mimetype, body_preview_bytes)

    if not request.content_length:
        return "", False

    # getattr: Flask types the stream as IO, werkzeug gives a LimitedStream.
    if getattr(request.stream, "is_exhausted", False):
        # Handler read request.stream directly, which werkzeug does not cache.
        return REQTAP_USER_FACING_MSG_BODY_CONSUMED, False

    return REQTAP_USER_FACING_MSG_BODY_NOT_READ, False


def _capture_response_body(response: Response, body_preview_bytes: int) -> tuple[str, bool]:
    """Preview the response body, or say why we left it alone.

    A body is skipped when reading it would destroy it, or when it isn't text.
    """
    # A streamed body is one-shot: reading it here is the only read anyone gets.
    # direct_passthrough covers send_file, is_streamed covers generators.
    if response.direct_passthrough or response.is_streamed:
        return "<skipped: streamed response>", False

    raw = response.get_data()
    try:
        # Strict: a decode failure here means binary, and errors="replace"
        # would store a screenful of U+FFFD instead of saying so.
        return redact_body_preview(
            raw, response.mimetype, body_preview_bytes, errors="strict"
        )
    except UnicodeDecodeError:
        return f"<skipped: binary response, {len(raw)} bytes>", False


def _redact(
    header_items: Iterable[tuple[str, str]], redact_headers: set[str]
) -> list[tuple[str, str]]:
    """Copy headers as pairs, masking automatic and custom sensitive names."""
    return [
        (
            key,
            REQTAP_USER_FACING_MSG_REDACTED
            if is_sensitive_key(key) or key.lower() in redact_headers
            else _trim_header(value),
        )
        for key, value in header_items
    ]


def _trim_header(value: str) -> str:
    """Cap one header value, saying how much was dropped.

    A server allows ~100 headers of up to 64 KB each, so uncapped values let a
    padded request pin megabytes in the buffer while its body stays tiny.
    """
    if len(value) <= MAX_HEADER_CHARS:
        return value
    return f"{value[:MAX_HEADER_CHARS]}… (+{len(value) - MAX_HEADER_CHARS} chars)"


def _elapsed_ms() -> float:
    """How long this request took, in milliseconds."""
    start: float = getattr(g, START_KEY, time.perf_counter())
    return (time.perf_counter() - start) * 1000
