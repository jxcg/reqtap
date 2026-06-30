"""The captured-request record and helpers for shaping it safely.

Everything here is a plain snapshot: stdlib dataclasses holding copied strings
and primitives, never live Flask/response objects. That's deliberate — see the
memory-safety notes on :class:`CapturedRequest`.
"""

from dataclasses import asdict, dataclass, field
from typing import Any


def truncate_text(text: str, max_bytes: int) -> tuple[str, bool]:
    """Cap ``text`` to ``max_bytes`` UTF-8 bytes, reporting whether it was cut.

    Measuring by encoded byte length (not character count) keeps the cap honest
    for non-ASCII bodies. This is a pure function so it can be unit-tested in
    isolation and reused by the Flask intercept layer without importing Flask.
    """
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    # Slicing bytes can land mid-character; ``errors="ignore"`` drops the
    # dangling partial byte rather than raising.
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


@dataclass
class CapturedRequest:
    """A snapshot of one request/response cycle.

    Built up across the request lifecycle (request fields first, response fields
    on the way out, traceback if it raised) and then handed to the store. Holds
    only copied primitives and strings — no references to Flask's ``request`` /
    ``response`` / ``session`` objects or to a live traceback — so storing it
    can't pin large object graphs or stack frames in memory.
    """

    # Identity / timing. ``id`` is stamped by the store on add().
    id: int = 0
    timestamp: float = 0.0  # epoch seconds, when the request started
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
        """Full JSON-serializable form, for the detail view."""
        return asdict(self)

    def to_summary(self) -> dict[str, Any]:
        """Lightweight form for the live feed — no bodies or headers.

        The feed can hold many rows, so it omits the heavy fields; the client
        fetches the full record via :meth:`to_dict` only when a row is opened.
        """
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "errored": self.traceback is not None,
        }
