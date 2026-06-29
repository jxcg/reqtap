"""Tests for the production-safety gate.

This is the most important test file in the project: if the gate ever returns
True when nobody asked for it, reqtap would expose request/traceback data where
it shouldn't. The integration assertion (the `/_reqtap` route 404s when reqtap
is off) is added once the Flask extension exists; here we pin the gate logic.
"""

import pytest
import logging
from reqtap.core.safety import is_active


def test_off_by_default():
    assert is_active() is False


def test_constructor_flag_activates():
    assert is_active(live_reqtap_requests=True) is True
