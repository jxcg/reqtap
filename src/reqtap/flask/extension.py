"""One-line entry point: ``ReqTap(app, live_reqtap_requests=True)``.

Does nothing unless the safety gate passes. When live, mounts the dashboard
at both ``/_reqtap/`` and the shorter ``/_rq/``.
"""

import logging

from flask import Flask, current_app, has_app_context

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
        # One store per app, not one per extension: init_app may be called for
        # several apps and each needs its own buffer.
        self._apps: list[Flask] = []

        # Hook reqtap into app
        if app is not None:
            self.init_app(app)

    @property
    def store(self) -> RingBufferStore | None:
        """The buffer for the app in play, or ``None`` when reqtap is off.

        Resolves through the app context when there is one, so the store always
        matches the app currently handling the request.
        """
        if has_app_context():
            in_context: RingBufferStore | None = current_app.extensions.get("reqtap")
            return in_context
        if not self._apps:
            return None
        if len(self._apps) > 1:
            raise RuntimeError(
                "ReqTap is installed on several apps, so tap.store is ambiguous here. "
                "Read it inside an app context, or use app.extensions['reqtap']."
            )
        only_app: RingBufferStore = self._apps[0].extensions["reqtap"]
        return only_app

    def init_app(self, app: Flask) -> None:
        """Hook reqtap into ``app`` if activated.

        Inactive: registers nothing; silent.
        Active: logs a warning so you know sensitive data is being recorded.
        """

        if not is_active(self.live_reqtap_requests):
            return

        store = RingBufferStore(capacity=self.buffer_size)
        # app.extensions is the store's home, so two apps cannot share one buffer.
        app.extensions["reqtap"] = store
        self._apps.append(app)

        intercept.install(
            app,
            store=store,
            body_preview_bytes=self.body_preview_bytes,
            redact_headers=self._redact_headers,
        )
        # Mount dashboard + API under both the full and short prefix. Without
        # this, /_reqtap and /_rq 404 even though capture works.
        blueprint = create_blueprint(store)
        app.register_blueprint(blueprint, url_prefix=DASHBOARD_PREFIX_LONG)
        app.register_blueprint(
            blueprint, name="reqtap_short", url_prefix=DASHBOARD_PREFIX_SHORT
        )
        logger.warning(
            "reqtap is ACTIVE: recording request/response bodies, headers, and "
            "tracebacks in memory! Never enable in production!"
        )
