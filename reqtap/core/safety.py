"""The production-safety gate — reqtap's single most important guard.

reqtap exposes request bodies, headers, and tracebacks, so it must never run
where it isn't wanted. Activation is funneled through one function,
:func:`is_active`, driven by explicit, framework-independent opt-in:
**reqtap is OFF unless you turn it on.**

Why not auto-detect "development mode"? Each framework signals it differently
(Flask uses ``app.debug``; FastAPI users typically rely on ``uvicorn --reload``
and leave ``app.debug`` False), and those conventions drift across versions.
Keying off them would make reqtap behave inconsistently from one framework — or
one release — to the next. Explicit opt-in is simpler and identical everywhere.

There are two ways to opt in, for two different needs:

- The ``LIVE_REQTAP_REQUESTS`` environment variable — the recommended toggle.
  It lives *outside* your code, so it can't be committed-on and shipped to
  production; prod simply never sets it.
- The ``live_reqtap_requests=True`` constructor flag — a visible in-code switch
  for when you'd rather flip it right there at ``ReqTap(app, ...)``. Convenient,
  but remember the value is committed, so don't leave it ``True`` for a deploy.
"""

import os


def is_active(live_reqtap_requests: bool = False) -> bool:
    """Return True only when reqtap should wire itself in.

    Active when *either* opt-in is present: the explicit constructor flag, or a
    truthy ``LIVE_REQTAP_REQUESTS`` environment variable. The default is OFF, so
    a bare ``ReqTap(app)`` line is safe in committed code.
    """
    return live_reqtap_requests
