"""Every hard-coded value reqtap depends on, in one place.

Kept here so a value can be found and changed without hunting through the
adapter modules that use it.
"""

from pathlib import Path

# The intercept layer skips this prefix so reqtap never captures itself.
DASHBOARD_PREFIX_LONG = "/_reqtap"
DASHBOARD_PREFIX_SHORT = "/_rq"

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

REDACTED = "<redacted>"

# Comfortably fits a session cookie or a JWT; the ceiling that matters is
# 100 headers x 200 records, not any single value.
MAX_HEADER_CHARS = 1024

# Per-request scratch keys on flask.g.
RECORD_KEY = "_reqtap_record"
START_KEY = "_reqtap_perf_start"
