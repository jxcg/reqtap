"""One-line entry point: ``ReqTap(app, live_reqtap_requests=True)``.

Does nothing unless the safety gate passes. When live, mounts ``/_reqtap/``.
"""

import logging

from flask import Flask

from reqtap.core.safety import is_active
from reqtap.core.store import RingBufferStore
from reqtap.flask import intercept
from reqtap.flask.dashboard import DASHBOARD_PREFIX, create_blueprint

logger = logging.getLogger("reqtap")

DEFAULT_REDACT_HEADERS = ["Authorization", "Cookie"]


class ReqTap:
    """Captures requests when activated. Opens ``/_reqtap/`` for inspection.

    Use ``ReqTap(app, ...)`` or ``ReqTap().init_app(app)``.
    ``live_reqtap_requests`` turns it on; other args tune buffer, body size,
    and header redaction.
    """

    def __init__(
        self,
        app: Flask | None = None,
        *,
        live_reqtap_requests: bool = False,
        buffer_size: int = 200,
        max_body_bytes: int = 64_000,
        redact_headers: list[str] | None = None,
    ) -> None:
        self.live_reqtap_requests = live_reqtap_requests
        self.buffer_size = buffer_size
        self.max_body_bytes = max_body_bytes
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
            max_body_bytes=self.max_body_bytes,
            redact_headers=self._redact_headers,
        )
        # Mount dashboard + API. Without this, /_reqtap 404s even though capture works.
        app.register_blueprint(
            create_blueprint(self.store), url_prefix=DASHBOARD_PREFIX
        )
        logger.warning(
            "reqtap is LIVE: recording request/response bodies, headers, and "
            "tracebacks in memory. Do not enable in production."
        )
