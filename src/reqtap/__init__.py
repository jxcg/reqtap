"""reqtap — a wiretap for your web app's requests.

Public API:
    from reqtap import ReqTap

``ReqTap`` is exported lazily: it lives in the Flask adapter, which the core
doesn't depend on. Accessing it imports the adapter on demand, and if Flask
isn't installed you get a clear hint instead of an obscure ImportError deep in
the call stack.
"""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

try:
    # Single source of truth: the version declared in pyproject.toml, read back
    # from the installed package metadata rather than duplicated here.
    __version__ = version("reqtap")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"

__all__ = ["ReqTap", "__version__"]


def __getattr__(name: str) -> Any:
    """Lazily resolve ``ReqTap`` from the Flask adapter (PEP 562).

    This keeps ``import reqtap`` working with zero third-party packages while
    still offering ``from reqtap import ReqTap`` when Flask is present.
    """
    if name == "ReqTap":
        try:
            # Import our ReqTap class module with Flask present within extension
            from reqtap.flask.extension import ReqTap
        except ImportError as exc:
            raise ImportError(
                "ReqTap requires Flask. Install it with: pip install reqtap[flask]"
            ) from exc
        return ReqTap
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
