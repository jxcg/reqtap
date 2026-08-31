"""Open ``/_reqtap/`` in a browser to browse captured traffic.

Small UI plus JSON API (list, detail, clear).
Built as a factory so each ReqTap instance gets its own store, no globals.
The interceptor ignores this path, so the dashboard never captures itself.
"""

import json
from ipaddress import IPv6Address, ip_address
from typing import Any
from urllib.parse import urlsplit

import jinja2
from flask import Blueprint, Response, abort, request

from reqtap import __version__
from reqtap.core.constants import UI_DIRECTORY
from reqtap.core.store import RingBufferStore

# reqtap's own environment, never the host app's: flask.render_template would
# apply the inspected app's autoescape settings to a page full of its own data.
_JINJA = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(UI_DIRECTORY)),
    autoescape=True,
)


def create_blueprint(store: RingBufferStore) -> Blueprint:
    """Build the dashboard blueprint for one store.

    Fresh blueprint per ReqTap instance so tests can spin up multiple apps.
    """
    blueprint = Blueprint(
        "reqtap",
        __name__,
        static_folder=str(UI_DIRECTORY),
        static_url_path="/static",
    )

    @blueprint.before_request
    def require_local_access() -> None:
        """Keep captured data away from remote clients and from other websites.

        The address alone is not enough: a website can point one of its own
        names at 127.0.0.1 (DNS rebinding) and have a visitor's browser fetch
        this dashboard, so the connection really is local. The Host header
        still carries the attacker's name, which is what gives it away.

        Proxy headers are not trusted for either value: see _before_proxy_fix.
        """
        if not _is_loopback_address(_before_proxy_fix("REMOTE_ADDR", request.remote_addr)):
            abort(403)

        if not _is_local_host_name(_before_proxy_fix("HTTP_HOST", request.host) or ""):
            abort(403)

        # A request another site started must not be able to read this data
        # back, which is what a CORS-enabled host app would otherwise allow.
        # Following a link here is the exception: the page that sent you
        # cannot read what comes back, and framing is refused separately by
        # frame-ancestors below. A link is always a plain GET of a whole page,
        # so anything else is a script or a frame, whatever it labels itself.
        started_elsewhere = request.headers.get("Sec-Fetch-Site", "none") not in (
            "none",
            "same-origin",
        )
        followed_a_link = (
            request.method == "GET"
            and request.headers.get("Sec-Fetch-Mode") == "navigate"
            and request.headers.get("Sec-Fetch-Dest") == "document"
        )
        if started_elsewhere and not followed_a_link:
            abort(403)
        if request.headers.get("Origin"):
            abort(403)

    @blueprint.after_request
    def security_headers(response: Response) -> Response:
        """Captured data must not be cached, and nothing here may execute.

        ``style-src 'unsafe-inline'`` covers the page's inline ``<style>``;
        ``default-src 'none'`` denies scripts, images, fonts and connections,
        so an injection that survives autoescape has nothing to run.
        """
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
        )
        return response

    @blueprint.get("/")
    def index() -> Response:
        """Render the dashboard, 
        feed follows newest first."""
        page = _JINJA.get_template("feed.html.j2").render(
            records=list(reversed(store.list())), version=__version__
        )
        return Response(page, mimetype="text/html")

    @blueprint.get("/api/requests")
    def list_requests() -> Response:
        """Lightweight summaries, newest first.

        Pass ``?since=<id>`` to fetch only records newer than that id.
        """
        since = request.args.get("since", type=int)
        records = store.list()
        if since is not None:
            records = [record for record in records if record.id > since]

        # Store is oldest-first; feed wants newest-first.
        summaries = [record.to_summary() for record in reversed(records)]
        return _json_response({"requests": summaries})

    @blueprint.get("/api/requests/<int:record_id>")
    def get_request(record_id: int) -> Response:
        """Full detail for one request. 404 if it was evicted from the buffer."""
        record = store.get(record_id)
        if record is None:
            return _json_response(
                {"error": f"No captured request with id {record_id}."}, status=404
            )
        return _json_response(record.to_dict())

    @blueprint.delete("/api/requests")
    def clear_requests() -> Response:
        """Clear the buffer."""
        store.clear()
        return _json_response({"cleared": True})

    return blueprint


def _is_local_host_name(host: str) -> bool:
    """Return whether a ``Host`` header names this machine.

    ``urlsplit`` does the fiddly parts for us: it drops the port, unwraps the
    ``[...]`` around an IPv6 address, and lowercases the name (Host is
    case-insensitive, so ``LOCALHOST`` must be accepted).
    """
    # "evil.com@localhost": urlsplit would drop everything before the "@" and
    # see plain "localhost". Werkzeug rejects such a Host before we get here,
    # but refuse it ourselves so this function is safe on its own.
    if "@" in host:
        return False

    try:
        name = urlsplit(f"//{host}").hostname
    except ValueError:
        # Malformed, e.g. an unclosed IPv6 bracket.
        return False

    if not name:
        return False

    # "localhost." and "localhost" are the same name to a resolver.
    name = name.removesuffix(".")

    # Browsers resolve localhost and anything under it to loopback (RFC 6761),
    # so "myapp.localhost" is us. "localhost.evil.com" is not, and does not
    # match either branch.
    if name == "localhost" or name.endswith(".localhost"):
        return True

    return _is_loopback_address(name)


def _before_proxy_fix(key: str, current: str | None) -> str | None:
    """The value the server saw, before any proxy header rewrote it.

    ProxyFix takes the address and host from headers the caller sets, so a
    remote client can hand itself both. It stashes the originals first, and
    those are what the gate must judge: the real peer, not the claimed one.
    """
    original: dict[str, str | None] | None = request.environ.get("werkzeug.proxy_fix.orig")
    if original is None:
        return current
    return original.get(key)


def _is_loopback_address(address: str | None) -> bool:
    """Return whether a WSGI peer address is an IPv4 or IPv6 loopback."""
    if address is None:
        return False

    try:
        parsed = ip_address(address)
    except ValueError:
        return False

    if parsed.is_loopback:
        return True

    # Some WSGI servers represent IPv4 peers as IPv4-mapped IPv6 addresses.
    return (
        isinstance(parsed, IPv6Address)
        and parsed.ipv4_mapped is not None
        and parsed.ipv4_mapped.is_loopback
    )


def _json_response(payload: dict[str, Any], status: int = 200) -> Response:
    """JSON response without flask.jsonify.

    Keeps reqtap's wire format independent of the host app's JSON settings.
    """
    return Response(
        json.dumps(payload, default=str),
        status=status,
        mimetype="application/json",
    )
