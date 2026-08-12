"""The dashboard page renders captured requests as HTML.

Rendering happens in Python, so these assert real content rather than merely
that some page was served.
"""

from typing import Any

from flask import Flask

from reqtap import ReqTap


def build_app(**reqtap_kwargs: Any) -> tuple[Flask, ReqTap]:
    """An app with one endpoint and reqtap mounted."""
    app = Flask(__name__)

    @app.get("/hello")
    def hello() -> str:
        """A plain 200 to capture."""
        return "ok"

    tap = ReqTap(app, live_reqtap_requests=True, **reqtap_kwargs)
    return app, tap


def test_captured_request_appears_in_the_page() -> None:
    """The whole point: a request that happened is visible in the feed."""
    app, _ = build_app()
    client = app.test_client()
    client.get("/hello")

    page = client.get("/_reqtap/").data.decode("utf-8")

    assert "GET" in page
    assert "/hello" in page
    assert "200" in page


def test_paths_are_escaped_in_the_page() -> None:
    """Paths are attacker-controlled; the dashboard renders them as text, not markup."""
    app, _ = build_app()
    client = app.test_client()
    client.get("/<script>alert(1)</script>")

    page = client.get("/_reqtap/").data.decode("utf-8")

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_newest_request_is_first() -> None:
    """The feed reads newest-first; the store is oldest-first."""
    app, _ = build_app()
    client = app.test_client()
    client.get("/first")
    client.get("/second")

    page = client.get("/_reqtap/").data.decode("utf-8")

    assert page.index("/second") < page.index("/first")


def test_failures_are_marked_up_by_severity() -> None:
    """4xx reads amber, 5xx red, and a raising handler is red whatever its status."""
    app, _ = build_app()

    @app.get("/missing")
    def missing() -> tuple[str, int]:
        """A plain 404."""
        return "gone", 404

    @app.get("/boom")
    def boom() -> str:
        """Raises, so the record carries a traceback."""
        raise RuntimeError("kaboom")

    client = app.test_client()
    client.get("/hello")
    client.get("/missing")
    client.get("/boom")

    page = client.get("/_reqtap/").data.decode("utf-8")

    assert '<td class="warn">404</td>' in page
    assert '<td class="error">500</td>' in page
    assert '<td class="">200</td>' in page


def test_dashboard_denies_scripts() -> None:
    """CSP is the layer that survives an escaping mistake."""
    app, _ = build_app()

    response = app.test_client().get("/_reqtap/")

    assert response.headers["Content-Security-Policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'"
    )
    assert response.headers["Cache-Control"] == "no-store"
