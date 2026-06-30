"""The ``ReqTap`` extension — the one-line entry point.

``ReqTap(app, live_reqtap_requests=True)`` wires capture into a Flask app, but
only after the safety gate says so. When it doesn't, this object registers
nothing and intercepts nothing.
"""

import logging

from flask import Flask

from reqtap.core.safety import is_active
from reqtap.core.store import RingBufferStore
from reqtap.flask import intercept

logger = logging.getLogger("reqtap")

DEFAULT_REDACT_HEADERS = ["Authorization", "Cookie"]


class ReqTap:
    """Flask extension that passively captures requests when activated.

    Supports both the direct form ``ReqTap(app, ...)`` and the app-factory form
    (``tap = ReqTap(...)`` then ``tap.init_app(app)``). The three config knobs
    tune capture behavior; ``live_reqtap_requests`` is the activation switch and
    the single source of truth for whether reqtap runs at all.
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
        # Normalize to a lowercase set once, so per-request matching is cheap and
        # case-insensitive.
        self._redact_headers = {
            name.lower() for name in (redact_headers or DEFAULT_REDACT_HEADERS)
        }
        # Stays None while inactive — a useful, checkable signal that reqtap is off.
        self.store: RingBufferStore | None = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Wire capture into ``app`` — but only if activated.

        The safety gate is checked first, before anything is registered. When
        inactive we log a quiet hint and return, so a committed ``ReqTap(app)``
        line is completely inert.
        """
        if not is_active(self.live_reqtap_requests):
            logger.info(
                "reqtap: inactive — pass live_reqtap_requests=True to ReqTap() to record requests"
            )
            return

        self.store = RingBufferStore(capacity=self.buffer_size)
        intercept.install(
            app,
            store=self.store,
            max_body_bytes=self.max_body_bytes,
            redact_headers=self._redact_headers,
        )
        logger.info("reqtap: LIVE — recording requests")
