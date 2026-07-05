"""Flask (WSGI) adapter

All Flask-specific coupling lives under this package, keeping ``reqtap.core``
framework-agnostic.
"""

from reqtap.flask.extension import ReqTap
__all__ = ["ReqTap"]