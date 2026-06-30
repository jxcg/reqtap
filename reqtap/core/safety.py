"""The production-safety gate — reqtap's single most important guard.

reqtap exposes request bodies, headers, and tracebacks, so it must never run
where it isn't wanted. Activation is funneled through one function,
:func:`is_active`, driven by a single explicit, framework-independent opt-in:
**reqtap is OFF unless you turn it on** via the ``live_reqtap_requests`` flag.

Why not auto-detect "development mode"? Each framework signals it differently
(Flask uses ``app.debug``; FastAPI users typically rely on ``uvicorn --reload``
and leave ``app.debug`` False), and those conventions drift across versions.
Keying off them would make reqtap behave inconsistently from one framework — or
one release — to the next. One explicit constructor flag is the single source
of truth: simpler, identical everywhere, and trivial to reason about.
"""


def is_active(live_reqtap_requests: bool = False) -> bool:
    """Return True only when reqtap should wire itself in.

    Active only when ``live_reqtap_requests=True`` is passed to ``ReqTap``. The
    default is OFF, so a bare ``ReqTap(app)`` line is inert in committed code.
    """
    return live_reqtap_requests
