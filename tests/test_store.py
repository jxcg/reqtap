"""Tests for the model helpers and the ring-buffer store.

These pin the memory-safety guarantees that matter most: the buffer stays
bounded, the oldest records are evicted, and body truncation actually caps
size. If any of these regress, reqtap could grow without limit inside the host
process.
"""

from reqtap.core.models import CapturedRequest, decode_preview
from reqtap.core.store import RingBufferStore


def make_record(method: str = "GET", path: str = "/") -> CapturedRequest:
    return CapturedRequest(method=method, path=path)


# --- decode_preview --------------------------------------------------------


def test_preview_leaves_small_text_untouched() -> None:
    text, was_truncated = decode_preview(b"hello", max_bytes=64)
    assert text == "hello"
    assert was_truncated is False


def test_preview_caps_to_byte_budget() -> None:
    text, was_truncated = decode_preview(b"x" * 1000, max_bytes=10)
    assert was_truncated is True
    assert len(text.encode("utf-8")) <= 10


def test_preview_measures_bytes_not_characters() -> None:
    # "é" is two UTF-8 bytes, so a 3-byte budget fits only one character.
    text, was_truncated = decode_preview("ééé".encode(), max_bytes=3)
    assert was_truncated is True
    assert len(text.encode("utf-8")) <= 3


def test_preview_does_not_decode_past_the_budget() -> None:
    # A huge byte sequence must not become a huge string before it is trimmed.
    text, _ = decode_preview(b"x" * 10_000_000, max_bytes=8)
    assert text == "xxxxxxxx"


# --- RingBufferStore -------------------------------------------------------


def test_add_assigns_incrementing_ids() -> None:
    store = RingBufferStore(capacity=10)
    first = store.add(make_record())
    second = store.add(make_record())
    assert (first.id, second.id) == (1, 2)


def test_list_returns_all_oldest_first() -> None:
    store = RingBufferStore(capacity=10)
    store.add(make_record(path="/a"))
    store.add(make_record(path="/b"))
    paths = [r.path for r in store.list()]
    assert paths == ["/a", "/b"]


def test_get_by_id_and_missing() -> None:
    store = RingBufferStore(capacity=10)
    record = store.add(make_record(path="/found"))
    assert store.get(record.id) is record
    assert store.get(9999) is None


def test_capacity_is_bounded_and_evicts_oldest() -> None:
    store = RingBufferStore(capacity=3)
    for i in range(10):
        store.add(make_record(path=f"/{i}"))

    records = store.list()
    assert len(records) == 3  # never grows past capacity
    # Only the three most recent survive; the oldest were evicted.
    assert [r.path for r in records] == ["/7", "/8", "/9"]


def test_evicted_records_are_unreachable() -> None:
    store = RingBufferStore(capacity=2)
    evicted = store.add(make_record(path="/old"))
    store.add(make_record(path="/mid"))
    store.add(make_record(path="/new"))
    # The first record fell out of the buffer, so it can't be fetched anymore.
    assert store.get(evicted.id) is None


def test_clear_empties_the_buffer() -> None:
    store = RingBufferStore(capacity=5)
    store.add(make_record())
    store.clear()
    assert store.list() == []


def test_to_summary_omits_heavy_fields() -> None:
    record = CapturedRequest(method="POST", path="/x", request_body="big payload")
    summary = record.to_summary()
    assert summary["method"] == "POST"
    assert "request_body" not in summary
    assert summary["errored"] is False
