"""reqtap: a dev-time wiretap for web app HTTP traffic.

Add one line to Flask, hit your routes, then peek at what went in and out
(headers, bodies, status, errors) at ``/_reqtap/`` or the JSON API below it.

Quick start::

    from flask import Flask
    from reqtap import ReqTap

    app = Flask(__name__)
    ReqTap(app, live_reqtap_requests=True)

In-memory only, off by default. Pass ``live_reqtap_requests=True`` to turn it on.
Don't use this in production.
"""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

try:
    # Version from pyproject.toml, via installed package metadata.
    __version__ = version("reqtap")
except PackageNotFoundError:  # source checkout, not pip-installed yet
    __version__ = "0.0.0"

__all__ = ["ReqTap", "__version__"]


def __getattr__(name: str) -> Any:
    """Load ``ReqTap`` from the Flask adapter only when you ask for it.

    Lets ``import reqtap`` work without Flask installed.
    """
    if name == "ReqTap":
        try:
            # Pull in the Flask adapter (needs Flask installed).
            from reqtap.flask.extension import ReqTap
        except ImportError as exc:
            raise ImportError(
                "ReqTap requires Flask. Install it with: pip install reqtap[flask]"
            ) from exc
        return ReqTap
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
