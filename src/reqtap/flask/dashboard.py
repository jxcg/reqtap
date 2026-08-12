"""Open ``/_reqtap/`` in a browser to browse captured traffic.

Small UI plus JSON API (list, detail, clear).
Built as a factory so each ReqTap instance gets its own store, no globals.
The interceptor ignores this path, so the dashboard never captures itself.
"""

import json
from ipaddress import IPv6Address, ip_address
from typing import Any

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
        """Keep captured application data inaccessible to remote clients."""
        if not _is_loopback_address(request.remote_addr):
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
            "default-src 'none'; style-src 'unsafe-inline'"
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
