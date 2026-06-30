"""Tests for the model helpers and the ring-buffer store.

These pin the memory-safety guarantees that matter most: the buffer stays
bounded, the oldest records are evicted, and body truncation actually caps
size. If any of these regress, reqtap could grow without limit inside the host
process.
"""

from reqtap.core.models import CapturedRequest, truncate_text
from reqtap.core.store import RingBufferStore


def make_record(method: str = "GET", path: str = "/") -> CapturedRequest:
    return CapturedRequest(method=method, path=path)


# --- truncate_text ---------------------------------------------------------


def test_truncate_leaves_small_text_untouched():
    text, was_truncated = truncate_text("hello", max_bytes=64)
    assert text == "hello"
    assert was_truncated is False


def test_truncate_caps_to_byte_budget():
    text, was_truncated = truncate_text("x" * 1000, max_bytes=10)
    assert was_truncated is True
    assert len(text.encode("utf-8")) <= 10


def test_truncate_measures_bytes_not_characters():
    # "é" is two UTF-8 bytes, so a 3-byte budget fits only one character.
    text, was_truncated = truncate_text("ééé", max_bytes=3)
    assert was_truncated is True
    assert len(text.encode("utf-8")) <= 3


# --- RingBufferStore -------------------------------------------------------


def test_add_assigns_incrementing_ids():
    store = RingBufferStore(capacity=10)
    first = store.add(make_record())
    second = store.add(make_record())
    assert (first.id, second.id) == (1, 2)


def test_list_returns_all_oldest_first():
    store = RingBufferStore(capacity=10)
    store.add(make_record(path="/a"))
    store.add(make_record(path="/b"))
    paths = [r.path for r in store.list()]
    assert paths == ["/a", "/b"]


def test_get_by_id_and_missing():
    store = RingBufferStore(capacity=10)
    record = store.add(make_record(path="/found"))
    assert store.get(record.id) is record
    assert store.get(9999) is None


def test_capacity_is_bounded_and_evicts_oldest():
    store = RingBufferStore(capacity=3)
    for i in range(10):
        store.add(make_record(path=f"/{i}"))

    records = store.list()
    assert len(records) == 3  # never grows past capacity
    # Only the three most recent survive; the oldest were evicted.
    assert [r.path for r in records] == ["/7", "/8", "/9"]


def test_evicted_records_are_unreachable():
    store = RingBufferStore(capacity=2)
    evicted = store.add(make_record(path="/old"))
    store.add(make_record(path="/mid"))
    store.add(make_record(path="/new"))
    # The first record fell out of the buffer, so it can't be fetched anymore.
    assert store.get(evicted.id) is None


def test_clear_empties_the_buffer():
    store = RingBufferStore(capacity=5)
    store.add(make_record())
    store.clear()
    assert store.list() == []


def test_to_summary_omits_heavy_fields():
    record = CapturedRequest(method="POST", path="/x", request_body="big payload")
    summary = record.to_summary()
    assert summary["method"] == "POST"
    assert "request_body" not in summary
    assert summary["errored"] is False
