"""Shared test fixtures.

Activation is controlled explicitly (the ``live_reqtap_requests`` flag or the
``LIVE_REQTAP_REQUESTS`` env var), so a single plain app suffices — tests flip
reqtap on or off themselves rather than relying on any app attribute.
"""

import pytest
from flask import Flask


@pytest.fixture
def app() -> Flask:
    """A minimal Flask app for wiring reqtap into."""
    return Flask(__name__)
