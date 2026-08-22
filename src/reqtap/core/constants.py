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

# Short names that are also fragments of ordinary English words, so they are
# matched as whole words rather than substrings: as substrings "oauth" hits
# "coauthor" and "otp" hits "footpath".
SENSITIVE_KEY_WORDS = (
    "auth",
    "oauth",
    "otp",
)

# Substrings matched case-insensitively against decoded query keys and header
# names. This catches unlisted variants such as "reset_token", "apiKey", and
# "X-Vendor-Secret" while leaving ordinary names such as "passenger" alone.
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
