"""Open ``/_reqtap/`` in a browser to browse captured traffic.

Small UI plus JSON API (list, detail, clear).
Built as a factory so each ReqTap instance gets its own store, no globals.
The interceptor ignores this path, so the dashboard never captures itself.
"""

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, request, send_from_directory

from reqtap.core.store import RingBufferStore

#: Dashboard mount path. Intercept layer imports this to skip self-traffic.
DASHBOARD_PREFIX = "/_reqtap"

#: Bundled HTML lives in the package. Works from source tree or installed wheel.
_UI_DIRECTORY = Path(__file__).parent.parent / "dashboard"


def create_blueprint(store: RingBufferStore) -> Blueprint:
    """Build the dashboard blueprint for one store.

    Fresh blueprint per ReqTap instance so tests can spin up multiple apps.
    """
    blueprint = Blueprint(
        "reqtap",
        __name__,
        static_folder=str(_UI_DIRECTORY),
        static_url_path="/static",
    )

    @blueprint.get("/")
    def index() -> Response:
        """Serve the dashboard shell."""
        return send_from_directory(_UI_DIRECTORY, "index.html")

    @blueprint.get("/api/requests")
    def list_requests() -> Response:
        """Lightweight list for the live feed, newest first.

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
        """Clear the buffer ("clear feed" in the UI)."""
        store.clear()
        return _json_response({"cleared": True})

    return blueprint


def _json_response(payload: dict[str, Any], status: int = 200) -> Response:
    """JSON response without flask.jsonify.

    Keeps reqtap's wire format independent of the host app's JSON settings.
    """
    return Response(
        json.dumps(payload, default=str),
        status=status,
        mimetype="application/json",
    )
