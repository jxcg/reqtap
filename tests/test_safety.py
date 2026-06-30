"""Tests for the production-safety gate.

This is the most important test file in the project: if the gate ever returns
True when nobody asked for it, reqtap would expose request/traceback data where
it shouldn't. The integration assertion (the `/_reqtap` route 404s when reqtap
is off) is added once the Flask extension exists; here we pin the gate logic.
"""

import logging

import pytest

from reqtap.core.safety import is_active

logger = logging.getLogger(__name__)


def test_off_by_default():
    assert is_active() is False


@pytest.mark.parametrize(
    ("live_reqtap_requests", "expected"),
    [
        (True, True),
        (False, False),
    ],
)
def test_flag_drives_activation(live_reqtap_requests, expected, caplog):
    """The flag is the single source of truth: its value is the gate's answer.

    Parametrized over both inputs so one test body covers on and off. The
    logging line + `caplog` assertion double as the pattern for later tests
    that need to verify what reqtap logs.
    """
    with caplog.at_level(logging.INFO):
        logger.info("LIVE_REQTAP_REQUESTS=%s", live_reqtap_requests)

    assert is_active(live_reqtap_requests) is expected
    assert f"LIVE_REQTAP_REQUESTS={live_reqtap_requests}" in caplog.text
