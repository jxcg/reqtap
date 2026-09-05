"""Framework-neutral redaction for query strings and structured body previews."""

import json
import re
from typing import Any
from urllib.parse import unquote_plus

from reqtap.core.constants import (
    REQTAP_USER_FACING_MSG_BODY_REDACTION_FAILED,
    REQTAP_USER_FACING_MSG_REDACTED,
    SENSITIVE_KEY_PATTERNS,
    SENSITIVE_KEY_WORDS,
)
from reqtap.core.models import decode_preview

# Separators, or the gap between a lowercase letter and an uppercase one.
_WORD_BOUNDARY = re.compile(r"[^A-Za-z0-9]+|(?<=[a-z0-9])(?=[A-Z])")


class _JSONNumber(str):
    """Keep number tokens without float rounding or integer conversion limits."""


class _JSONObject(list[tuple[str, Any]]):
    """Keep every object member, including repeated names, distinct from arrays."""


def redact_body_preview(
    raw: bytes,
    mimetype: str | None,
    max_bytes: int,
    *,
    errors: str = "replace",
) -> tuple[str, bool]:
    """Redact supported structured bodies before retaining a bounded preview.

    JSON and URL-encoded forms expose field names, so values on sensitive-looking
    keys can be masked without discarding the useful shape of the payload. A body
    that is too large or malformed is hidden rather than falling back to raw text.
    Other media types keep the existing byte-bounded preview behavior.
    """
    normalized_mimetype = (mimetype or "").lower()
    is_json = normalized_mimetype == "application/json" or normalized_mimetype.endswith("+json")
    is_form = normalized_mimetype == "application/x-www-form-urlencoded"

    if not raw or (not is_json and not is_form):
        return decode_preview(raw, max_bytes, errors=errors)

    # Parsing an arbitrarily large body would make the preview limit meaningless
    # as a resource bound. Do not retain an unredacted prefix when safe parsing is
    # unavailable: a credential can occur anywhere in the structured document.
    if len(raw) > max_bytes:
        return _redaction_failure_preview(max_bytes, truncated=True)

    try:
        if is_json:
            payload = json.loads(
                raw,
                parse_int=_JSONNumber,
                parse_float=_JSONNumber,
                parse_constant=_JSONNumber,
                object_pairs_hook=_JSONObject,
            )
            redacted = _redact_json_value(payload)
        else:
            redacted = redact_query_string(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        return _redaction_failure_preview(max_bytes, truncated=False)

    # JSON permits escaped lone surrogates; keep them escaped while ordinary
    # Unicode stays UTF-8, without unnecessarily expanding the preview.
    return decode_preview(
        redacted.encode("utf-8", errors="backslashreplace"), max_bytes, errors=errors
    )


def redact_query_string(query_string: str) -> str:
    """Mask credential-looking values while preserving pair order and spelling."""
    redacted = []
    for pair in query_string.split("&"):
        if not pair:
            continue
        key, separator, value = pair.partition("=")
        # Decode only for matching. The stored key keeps the spelling the caller
        # sent, including percent escapes and repeated fields.
        if separator and is_sensitive_key(unquote_plus(key)):
            value = REQTAP_USER_FACING_MSG_REDACTED
        redacted.append(f"{key}{separator}{value}")
    return "&".join(redacted)


def is_sensitive_key(key: str) -> bool:
    """Return whether a decoded field or header name looks sensitive."""
    lowered = key.lower()
    words = _split_words(key)
    if any(word in words for word in SENSITIVE_KEY_WORDS):
        return True
    return any(pattern in lowered for pattern in SENSITIVE_KEY_PATTERNS)


def _redact_json_value(value: Any) -> str:
    """Serialize parsed JSON while masking sensitive object values."""
    if isinstance(value, _JSONNumber):
        return str(value)
    if isinstance(value, _JSONObject):
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False)
                + ":"
                + _redact_json_value(
                    REQTAP_USER_FACING_MSG_REDACTED if is_sensitive_key(key) else child
                )
                for key, child in value
            )
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(_redact_json_value(child) for child in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def _split_words(key: str) -> list[str]:
    """Break a key into lowercase words on separators and camelCase humps."""
    return [word.lower() for word in _WORD_BOUNDARY.split(key) if word]


def _redaction_failure_preview(max_bytes: int, *, truncated: bool) -> tuple[str, bool]:
    """Return a safe marker, still respecting unusually small preview limits."""
    marker, marker_truncated = decode_preview(
        REQTAP_USER_FACING_MSG_BODY_REDACTION_FAILED.encode("utf-8"),
        max_bytes,
    )
    return marker, truncated or marker_truncated
