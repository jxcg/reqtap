"""In module values that reqtap depends on, in one place."""

from pathlib import Path

# The intercept layer skips this prefix so reqtap never captures itself.
DASHBOARD_PREFIX_LONG = "/_reqtap"
DASHBOARD_PREFIX_SHORT = "/_rq"



# User-facing informational feedback messages
# The warning message displayed when reqtap is active.
REQTAP_USER_FACING_MSG_WARN = (
    "\n"
    "!!!!!!!!!!!!!!!!!!!!!!!! REQTAP WARNING !!!!!!!!!!!!!!!!!!!!!!!!\n"
    "[reqtap] reqtap is ACTIVE: recording request/response bodies, headers, and\n"
    "tracebacks in memory! NEVER ENABLE IN PRODUCTION!\n"
    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
)

# User-facing informational content messages
REQTAP_USER_FACING_MSG_REDACTED = "<redacted by reqtap>"
REQTAP_USER_FACING_MSG_MULTIPART = "<skipped: multipart upload>"
REQTAP_USER_FACING_MSG_BODY_CONSUMED = "<skipped: body consumed by handler>"
REQTAP_USER_FACING_MSG_BODY_NOT_READ = "<skipped: body not read by handler>"
REQTAP_USER_FACING_MSG_BODY_REDACTION_FAILED = (
    "<skipped: structured body could not be safely redacted>"
)

# Relative to this file, so constants.py must stay one level under reqtap/.
UI_DIRECTORY = Path(__file__).parent.parent / "dashboard"

# Matched as whole words, not substrings: "oauth" would otherwise hit
# "coauthor", and "otp" would hit "footpath".
SENSITIVE_KEY_WORDS = (
    "auth",
    "authenticate",
    "key",
    "oauth",
    "otp",
)

# Substrings, case-insensitive, over decoded query keys and header names, so
# unlisted variants like "X-Vendor-Secret" match and "passenger" does not.
SENSITIVE_KEY_PATTERNS = (
    "token",
    "secret",
    "password",
    "passwd",
    "passphrase",
    "pwd",
    "authorization",
    "authentication",
    "apikey",
    "api_key",
    "api-key",
    "signature",
    "credential",
    "session",
    "cookie",
    "csrf",
    "xsrf",
)

# Comfortably fits a session cookie or a JWT; the ceiling that matters is
# 100 headers x 200 records, not any single value.
MAX_HEADER_CHARS = 1024

# Per-request scratch keys on flask.g.
RECORD_KEY = "_reqtap_record"
START_KEY = "_reqtap_perf_start"
