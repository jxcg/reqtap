"""In-memory store for captured requests. Bounded and thread-safe."""

import threading
from collections import deque

from reqtap.core.models import CapturedRequest


class RingBufferStore:
    """Ring buffer of recent requests. Oldest drop off when full.

    Shared hand-off point between the interceptor (writer) and the dashboard
    (reader).
    """

    def __init__(self, capacity: int = 200) -> None:
        self._buffer: deque[CapturedRequest] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._next_id = 1

    def add(self, record: CapturedRequest) -> CapturedRequest:
        """Assign an id and append (newest last)."""
        with self._lock:
            record.id = self._next_id
            self._next_id += 1
            self._buffer.append(record)
        return record

    def list(self) -> list[CapturedRequest]:
        """All records, oldest first. Returns a copy so callers don't need the lock."""
        with self._lock:
            return list(self._buffer)

    def get(self, record_id: int) -> CapturedRequest | None:
        """Look up by id. None if evicted. Linear scan is fine at this size."""
        with self._lock:
            for record in self._buffer:
                if record.id == record_id:
                    return record
            return None

    def clear(self) -> None:
        """Wipe the buffer."""
        with self._lock:
            self._buffer.clear()
