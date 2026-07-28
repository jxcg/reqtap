"""The ``/_reqtap`` dashboard — a Flask blueprint serving the UI and its JSON API.

The blueprint is built by a factory rather than declared at module level because
the store it reads from belongs to a single :class:`~reqtap.flask.extension.ReqTap`
instance, created in ``init_app``. Closing over that store keeps the routes free
of globals and mirrors how ``intercept.install`` already receives its store.

Nothing here mutates captured data except the explicit clear endpoint, and the
interceptor skips this prefix entirely, so the dashboard never records itself.
"""

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, request, send_from_directory

from reqtap.core.store import RingBufferStore

#: Where the dashboard mounts. Defined here — the dashboard owns its own path —
#: and imported by the intercept layer so it knows which traffic to skip.
DASHBOARD_PREFIX = "/_reqtap"

#: Static UI assets ship inside the package, one level up from this adapter.
#: Resolved from ``__file__`` so it works from a source tree or an installed wheel.
_UI_DIRECTORY = Path(__file__).parent.parent / "dashboard"


def create_blueprint(store: RingBufferStore) -> Blueprint:
    """Build the dashboard blueprint bound to ``store``.

    Returns a fresh blueprint on every call so two ``ReqTap`` instances (say, in
    a test suite building several apps) never share routes or a store.
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
        """The live feed: lightweight summaries, newest first.

        Supports incremental polling via ``?since=<id>``: the client sends the
        highest id it already holds and gets back only what arrived after it.
        Without this the UI would re-download the whole buffer every poll.
        """
        since = request.args.get("since", type=int)
        records = store.list()
        if since is not None:
            records = [record for record in records if record.id > since]

        # The store keeps insertion order (oldest first); the feed reads newest first.
        summaries = [record.to_summary() for record in reversed(records)]
        return _json_response({"requests": summaries})

    @blueprint.get("/api/requests/<int:record_id>")
    def get_request(record_id: int) -> Response:
        """Full detail for one captured request, or 404 once it's been evicted."""
        record = store.get(record_id)
        if record is None:
            return _json_response(
                {"error": f"No captured request with id {record_id}."}, status=404
            )
        return _json_response(record.to_dict())

    @blueprint.delete("/api/requests")
    def clear_requests() -> Response:
        """Empty the buffer — the UI's "clear feed" action."""
        store.clear()
        return _json_response({"cleared": True})

    return blueprint


def _json_response(payload: dict[str, Any], status: int = 200) -> Response:
    """Serialize ``payload`` to a JSON response.

    Built directly rather than via ``flask.jsonify`` so the dashboard API stays
    independent of the host app's JSON settings — a custom encoder or sort order
    configured for the app's own endpoints shouldn't change reqtap's wire format.
    """
    return Response(
        json.dumps(payload, default=str),
        status=status,
        mimetype="application/json",
    )
