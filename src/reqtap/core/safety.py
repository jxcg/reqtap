"""Off by default. ReqTap only runs when you pass ``live_reqtap_requests=True``.

We don't auto-detect "dev mode" because every framework does it differently.
One explicit flag keeps behaviour predictable everywhere.
"""


def is_active(live_reqtap_requests: bool = False) -> bool:
    """True only when ``live_reqtap_requests=True`` was passed to ReqTap."""
    return live_reqtap_requests
