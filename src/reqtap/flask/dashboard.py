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
        """Keep captured application data away from remote clients and other sites.

        The peer address on its own is not enough. Any website can point one of
        its own names at 127.0.0.1 (DNS rebinding) and then make the visitor's
        browser fetch this dashboard: the connection really does come from the
        local machine, so the address check passes. The Host header still says
        the attacker's name, so checking it closes that hole.

        Assumes the client is talking to this app directly. Behind a proxy that
        Flask is told to trust (ProxyFix), both the peer address and Host come
        from headers the caller can set, so neither check can be relied on.
        That gap is tracked separately as issue #57.
        """
        if not _is_loopback_address(request.remote_addr):
            abort(403)

        if not _is_local_host_name(request.host):
            abort(403)

        # Browsers only send these on requests started by another site. If the
        # host app enables CORS, a correct-Host request from an attacker's page
        # would otherwise come back readable. Nothing on the dashboard makes
        # cross-site requests, so refusing them costs nothing.
        if request.headers.get("Origin"):
            abort(403)
        if request.headers.get("Sec-Fetch-Site", "none") not in ("none", "same-origin"):
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
