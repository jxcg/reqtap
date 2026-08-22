"""What one captured request looks like, plus helpers to trim bodies safely."""

import codecs
from dataclasses import asdict, dataclass, field
from typing import Any


def decode_preview(
    raw: bytes, max_bytes: int, errors: str = "replace"
) -> tuple[str, bool]:
    """Decode at most ``max_bytes`` of ``raw``. Returns (text, was_trimmed).

    Slices before decoding, so a 256 MiB body never becomes a 256 MiB str.
    The incremental decoder holds back a character the slice cut in half
    instead of reporting it as invalid, which matters for ``errors="strict"``.
    """
    was_trimmed = len(raw) > max_bytes
    decoder = codecs.getincrementaldecoder("utf-8")(errors)
    # final only when nothing was sliced off: an incomplete sequence is then a
    # genuinely bad byte, not a character the cut split in half.
    return decoder.decode(raw[:max_bytes], final=not was_trimmed), was_trimmed


@dataclass
class CapturedRequest:
    """Plain snapshot of one request/response cycle.

    Only strings and primitives, no live Flask objects. Safe to keep in memory.
    """

    # id is assigned by the store on add().
    id: int = 0
    timestamp: float = 0.0  # epoch seconds, when the request started
    timestamp_utc: str = ""  # same instant
    duration_ms: float | None = None

    # Request
    method: str = ""
    path: str = ""
    # Values on credential-looking keys are redacted at capture time.
    query_string: str = ""
    # Client addresses are deliberately not stored; the dashboard gate checks
    # the live request address instead.
    # Pairs, not a dict: HTTP allows a name to repeat (Set-Cookie, Vary, Link)
    # and a dict would keep only the last one.
    request_headers: list[tuple[str, str]] = field(default_factory=list)
    request_body: str = ""
    request_body_truncated: bool = False
    # Whole body on the wire, so a preview says how much it is a preview of.
    # Bytes, while the preview above is characters — the two differ on any
    # non-ASCII body, so never derive truncation by comparing them.
    request_body_total_bytes: int | None = None

    # Response
    status: int | None = None
    response_headers: list[tuple[str, str]] = field(default_factory=list)
    response_body: str = ""
    response_body_truncated: bool = False
    response_body_total_bytes: int | None = None

    # Error (only set if the handler raised)
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Everything, for the detail view."""
        return asdict(self)

    def to_summary(self) -> dict[str, Any]:
        """Light row for the JSON API. No bodies or headers."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "timestamp_utc": self.timestamp_utc,
            "duration_ms": self.duration_ms,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "errored": self.traceback is not None,
        }

    @property
    def status_class(self) -> str:
        """CSS class for the status cell.

        A handler that raised is an error even when the status says otherwise.
        """
        status = self.status or 0
        if self.traceback is not None or status >= 500:
            return "error"
        return "warn" if status >= 400 else ""
