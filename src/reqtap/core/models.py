"""What one captured request looks like, plus helpers to trim bodies safely."""

from dataclasses import asdict, dataclass, field
from typing import Any


def truncate_text(text: str, max_bytes: int) -> tuple[str, bool]:
    """Trim ``text`` to ``max_bytes`` UTF-8 bytes. Returns (text, was_trimmed)."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    # Byte slice can split a multibyte char; ignore the dangling fragment.
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


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
    query_string: str = ""
    remote_addr: str | None = None
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: str = ""
    request_body_truncated: bool = False

    # Response
    status: int | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    response_body: str = ""
    response_body_truncated: bool = False

    # Error (only set if the handler raised)
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Everything, for the detail view."""
        return asdict(self)

    def to_summary(self) -> dict[str, Any]:
        """Light row for the live feed. No bodies or headers."""
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
