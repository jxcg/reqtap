"""In-memory storage for captured requests.

The one v0.1 backend is :class:`RingBufferStore` — bounded and thread-safe,
which are the two properties that keep reqtap from degrading the host app.
"""

import threading
from collections import deque

from reqtap.core.models import CapturedRequest


class RingBufferStore:
    """A bounded, thread-safe buffer of the most recent captured requests.

    Bounded *by construction*: a ``deque(maxlen=capacity)`` silently drops the
    oldest record once full, so the buffer can never grow without limit no
    matter how much traffic flows. A lock guards every access because Flask's
    dev server handles requests on multiple threads.
    """

    def __init__(self, capacity: int = 200) -> None:
        self._buffer: deque[CapturedRequest] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_id = 1

    def add(self, record: CapturedRequest) -> CapturedRequest:
        """Stamp the record with a monotonic id and store it (newest last)."""
        with self._lock:
            record.id = self._next_id
            self._next_id += 1
            self._buffer.append(record)
        return record

    def list(self) -> list[CapturedRequest]:
        """Return a snapshot copy of all stored records, oldest first.

        Returning a fresh list (not the live deque) means callers can iterate
        freely without holding the lock or risking mutation mid-read.
        """
        with self._lock:
            return list(self._buffer)

    def get(self, record_id: int) -> CapturedRequest | None:
        """Look up a single record by id, or None if it's gone.

        A linear scan is fine here: the buffer is small (≤ capacity), and a side
        index would only have to be kept in sync with the deque's automatic
        eviction — more complexity than an O(n) walk is worth.
        """
        with self._lock:
            for record in self._buffer:
                if record.id == record_id:
                    return record
            return None

    def clear(self) -> None:
        """Drop all stored records (the dashboard's "clear feed" action)."""
        with self._lock:
            self._buffer.clear()
