"""reqtap must never pull a whole request into memory to record it."""

import tracemalloc

from flask import Flask

from reqtap import ReqTap
from reqtap.core.constants import (
    MAX_HEADER_CHARS,
    REQTAP_USER_FACING_MSG_BODY_NOT_READ,
)

MIB = 1024 * 1024
BODY_MIB = 4
PREVIEW = 8  # bytes we ask reqtap to keep


def test_big_body_does_not_blow_up_memory() -> None:
    app = Flask(__name__)

    # Handler ignores the body, so anything allocated during the request is reqtap's.
    @app.post("/upload")
    def upload() -> str:
        return "ok"

    rqtap = ReqTap(app, live_reqtap_requests=True, body_preview_bytes=PREVIEW)
    client = app.test_client()
    payload = b"a" * (BODY_MIB * MIB)  # built here, outside the measured window

    def send() -> None:
        client.post("/upload", data=payload, content_type="text/plain")

    send()  # warm up: the first request drags in imports we don't want counted
    tracemalloc.start()
    tracemalloc.reset_peak()
    send()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mib = peak / MIB
    record = rqtap.store.list()[-1]
    print(
        f"\n{BODY_MIB} MiB body, preview {PREVIEW} B"
        f" -> peak {peak_mib:.2f} MiB, kept {len(record.request_body)} B"
        f" of {record.request_body_total_bytes:,}"
    )

    # The marker proves reqtap left the body alone; the peak below is a
    # separate guard that it never reads one unbounded.
    assert record.request_body == REQTAP_USER_FACING_MSG_BODY_NOT_READ
    assert record.request_body_total_bytes == BODY_MIB * MIB  # header still gives the size
    # Allow runtime overhead while keeping capture far below the 4 MiB body size.
    assert peak_mib < 1.0, f"reqtap buffered the body: {peak_mib:.2f} MiB"


def test_padded_headers_do_not_fill_the_buffer() -> None:
    """Header limits keep a padded request from pinning megabytes in the buffer."""
    app = Flask(__name__)

    @app.get("/ping")
    def ping() -> str:
        return "ok"

    rqtap = ReqTap(app, live_reqtap_requests=True)
    junk = {f"X-Pad-{n}": "a" * 60_000 for n in range(97)}
    app.test_client().get("/ping", headers=junk)

    record = rqtap.store.list()[-1]
    stored = sum(len(value) for _, value in record.request_headers)
    print(f"\n97 headers x 60,000 chars sent -> {stored:,} chars stored")

    first_pad = next(value for name, value in record.request_headers if name == "X-Pad-0")
    assert first_pad.startswith("a" * MAX_HEADER_CHARS)
    assert "+58976 chars" in first_pad  # says what was dropped
    assert stored < 200_000, f"headers still uncapped: {stored:,} chars"
