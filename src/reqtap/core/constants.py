"""In module values that reqtap depends on, in one place."""

from pathlib import Path

# The intercept layer skips this prefix so reqtap never captures itself.
DASHBOARD_PREFIX_LONG = "/_reqtap"
DASHBOARD_PREFIX_SHORT = "/_rq"



# User-facing informational feedback messages
# The warning message displayed when reqtap is active.
REQTAP_FEEDBACK_MESSAGE_WARN = (
    "\n"
    "!!!!!!!!!!!!!!!!!!!!!!!! REQTAP WARNING !!!!!!!!!!!!!!!!!!!!!!!!\n"
    "[reqtap] reqtap is ACTIVE: recording request/response bodies, headers, and\n"
    "tracebacks in memory! NEVER ENABLE IN PRODUCTION!\n"
    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
)

# User-facing informational content messages
REQTAP_CONTENT_FACING_MESSAGE_REDACTED = "<redacted by reqtap>"

# Relative to this file, so constants.py must stay one level under reqtap/.
UI_DIRECTORY = Path(__file__).parent.parent / "dashboard"

# Matched case-insensitively on the whole name, so every variant needs its own
# entry: "Cookie" does not cover "Set-Cookie", and no X- prefix is implied.
# Pattern matching would cover unlisted vendor headers: see issue #44.
DEFAULT_REDACT_HEADERS = [
    "Authorization",
    "Proxy-Authorization",
    "Cookie",
    "Set-Cookie",
    "X-Api-Key",
    "X-Auth-Token",
    "X-Csrf-Token",
    "X-Xsrf-Token",
]

# Substrings matched case-insensitively against a query string key. Unlike the
# header list above, this catches unlisted variants: "reset_token" and
# "apiKey" both match. Kept narrow enough not to swallow ordinary parameters —
# "passphrase" matches, "passenger" does not. Issue #44 proposes the same
# approach for header names, and should share this list.
QUERY_REDACT_KEY_PATTERNS = (
    "token",
    "secret",
    "password",
    "passwd",
    "passphrase",
    "pwd",
    "auth",
    "apikey",
    "api_key",
    "api-key",
    "signature",
    "credential",
    "session",
    "csrf",
    "xsrf",
    "otp",
)

# Comfortably fits a session cookie or a JWT; the ceiling that matters is
# 100 headers x 200 records, not any single value.
MAX_HEADER_CHARS = 1024

# Per-request scratch keys on flask.g.
RECORD_KEY = "_reqtap_record"
START_KEY = "_reqtap_perf_start"
