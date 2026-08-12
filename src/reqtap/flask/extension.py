"""One-line entry point: ``ReqTap(app, live_reqtap_requests=True)``.

Does nothing unless the safety gate passes. When live, mounts the dashboard
at both ``/_reqtap/`` and the shorter ``/_rq/``.
"""

import logging

from flask import Flask

from reqtap.core.constants import (
    DASHBOARD_PREFIX_LONG,
    DASHBOARD_PREFIX_SHORT,
    DEFAULT_REDACT_HEADERS,
)
from reqtap.core.safety import is_active
from reqtap.core.store import RingBufferStore
from reqtap.flask import intercept
from reqtap.flask.dashboard import create_blueprint

logger = logging.getLogger("reqtap")


class ReqTap:
    """Captures requests when activated. Opens ``/_reqtap/`` for inspection.

    Use ``ReqTap(app, ...)`` or ``ReqTap().init_app(app)``.
    ``live_reqtap_requests`` turns it on; other args tune buffer, body preview
    size, and header redaction. ``body_preview_bytes`` caps how much of each
    body is kept and read — rejecting big requests is ``MAX_CONTENT_LENGTH``.
    """

    def __init__(
        self,
        app: Flask | None = None,
        *,
        live_reqtap_requests: bool = False,
        buffer_size: int = 200,
        body_preview_bytes: int = 64_000,
        redact_headers: list[str] | None = None,
    ) -> None:
        self.live_reqtap_requests = live_reqtap_requests
        self.buffer_size = buffer_size
        self.body_preview_bytes = body_preview_bytes
        # Lowercase once so header matching is fast and case-insensitive.
        self._redact_headers = {
            name.lower() for name in (redact_headers or DEFAULT_REDACT_HEADERS)
        }
        # None means reqtap is off. Handy to check in tests.
        self.store: RingBufferStore | None = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Hook reqtap into ``app`` if activated.

        Inactive: registers nothing, stays silent.
        Active: logs a warning so you know sensitive data is being recorded.
        """

        if not is_active(self.live_reqtap_requests):
            return

        self.store = RingBufferStore(capacity=self.buffer_size)
        intercept.install(
            app,
            store=self.store,
            body_preview_bytes=self.body_preview_bytes,
            redact_headers=self._redact_headers,
        )
        # Mount dashboard + API under both the full and short prefix. Without
        # this, /_reqtap and /_rq 404 even though capture works.
        blueprint = create_blueprint(self.store)
        app.register_blueprint(blueprint, url_prefix=DASHBOARD_PREFIX_LONG)
        app.register_blueprint(
            blueprint, name="reqtap_short", url_prefix=DASHBOARD_PREFIX_SHORT
        )
        logger.warning(
            "reqtap is ACTIVE: recording request/response bodies, headers, and "
            "tracebacks in memory! Never enable in production!"
        )
