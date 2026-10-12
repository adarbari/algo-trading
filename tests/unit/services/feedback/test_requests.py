"""``record_missing`` and ``FeatureRequestRecorder``: a draft's missing items become rows with the
span (clipped), never the sentence; one row per user, feature and exchange day; stamped with the
point-in-time columns; a full queue, a failing sink or a broken item never raises (ADR 0066
amendment)."""

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.data import StoreReader
from algotrade.data.feedback import read_feature_requests
from algotrade.services.feedback.request_recorder import FeatureRequestRecorder
from algotrade.services.feedback.requests import MAX_SPAN, record_missing, request_row
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.feedback_writer import FeedbackWriter

LATE = datetime(2026, 10, 3, 1, tzinfo=UTC)  # Fri 9pm in New York
NEXT = datetime(2026, 10, 3, 15, tzinfo=UTC)
RANGE = (date(2026, 10, 2), date(2026, 10, 3))


@dataclass
class Item:
    key: str | None = "fcf_yield"
    new_key_slug: str | None = None
    span: str = "free cash flow yield"
    closest: tuple[str, ...] = ("fcf_margin", "")
    feasibility: str = "NEEDS_SOURCE"


class Collect:
    def __init__(self, accept: bool = True) -> None:
        self.rows: list[dict[str, Any]] = []
        self.accept = accept

    def submit(self, row: Any) -> bool:
        self.rows.append(dict(row))
        return self.accept


def test_a_known_key_and_a_new_slug_make_rows_with_the_right_columns() -> None:
    sink = Collect()
    items = [Item(), Item(key=None, new_key_slug="gamma_squeeze", feasibility="odd", closest=())]
    assert record_missing(sink, "alice", items, call_id="c1", draft_session_id="s1", at=NEXT) == 2
    known, new = sink.rows
    assert (known["ref"], known["key"], known["new_slug"]) == ("fcf_yield", "fcf_yield", None)
    assert known["closest"] == "fcf_margin" and known["call_id"] == "c1"
    assert known["draft_session_id"] == "s1" and known["user"] == "alice" and known["ts"] == NEXT
    assert (new["ref"], new["key"], new["new_slug"]) == ("gamma_squeeze", None, "gamma_squeeze")
    assert new["feasibility"] == "UNCLEAR" and new["closest"] is None


def test_the_span_is_clipped_and_whitespace_folded_never_the_sentence() -> None:
    row = request_row("alice", Item(span="x " * 400), at=NEXT)
    assert row is not None and len(row["span"]) == MAX_SPAN and row["span"].endswith("…")
    assert set(row) == {
        "ts", "user", "ref", "key", "new_slug", "feasibility", "span", "closest", "call_id",
        "draft_session_id",
    }  # fmt: skip


def test_an_item_with_neither_key_nor_slug_is_skipped_and_a_refusing_sink_counts_none() -> None:
    sink = Collect()
    assert record_missing(sink, "a", [Item(key=None), Item(key="  ")], at=NEXT) == 0
    assert sink.rows == []
    assert record_missing(Collect(accept=False), "a", [Item()], at=NEXT) == 0


def test_a_failing_sink_or_item_never_raises(caplog: pytest.LogCaptureFixture) -> None:
    class Boom:
        def submit(self, row: Any) -> bool:
            raise RuntimeError("queue gone")

    with caplog.at_level(logging.ERROR):
        assert record_missing(Boom(), "a", [Item(), Item()], at=NEXT) == 0
        assert record_missing(Collect(), "a", [object()], at=NEXT) == 0  # type: ignore[list-item]
        assert record_missing(Collect(), "a", 5, at=NEXT) == 0  # type: ignore[arg-type]
    assert "not recorded" in caplog.text


def row(at: datetime, user: str = "alice", **over: Any) -> dict[str, Any]:
    made = request_row(user, Item(), at=at)
    assert made is not None
    return made | over


def test_rows_are_written_stamped_with_the_exchange_date_and_committed() -> None:
    backend = MemoryBackend()
    recorder = FeatureRequestRecorder(FeedbackWriter(backend), clock=lambda: NEXT)
    assert recorder.submit(row(LATE)) and recorder.submit(row(NEXT, "bob"))
    recorder.flush()
    frame = read_feature_requests(StoreReader(backend), *RANGE)
    assert frame is not None and len(frame) == 2
    by = frame.set_index("user")
    assert by.loc["alice", "session_date"] == date(2026, 10, 2)  # 21:00 in New York
    assert by.loc["bob", "session_date"] == date(2026, 10, 3)
    assert set(frame["source"]) == {"drafting_feedback"}
    assert (frame["knowledge_ts"] == frame["ts"]).all()
    assert frame["run_id"].str.startswith("feature_requests-").all()
    assert by.loc["bob", ["new_slug", "draft_session_id"]].isna().all()
    recorder.close()


def test_one_user_asking_twice_on_a_day_is_one_row_but_another_day_or_user_is_another() -> None:
    backend = MemoryBackend()
    recorder = FeatureRequestRecorder(FeedbackWriter(backend), clock=lambda: NEXT)
    recorder.submit(row(NEXT))
    recorder.submit(row(NEXT, span="again"))  # the same (user, ref, day): the later wins
    recorder.flush()
    recorder.submit(row(NEXT))  # a later batch, the same day: still one row (merge by key)
    recorder.submit(row(NEXT, "bob"))
    recorder.submit(row(LATE))  # the day before
    recorder.flush()
    frame = read_feature_requests(StoreReader(backend), *RANGE)
    assert frame is not None and len(frame) == 3
    assert sorted(zip(frame["user"], frame["session_date"], strict=True)) == [
        ("alice", date(2026, 10, 2)), ("alice", date(2026, 10, 3)), ("bob", date(2026, 10, 3)),
    ]  # fmt: skip
    recorder.close()


def test_a_full_queue_drops_the_row_and_logs_never_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gate = threading.Event()

    class Slow(FeedbackWriter):
        def publishing(self, run_id: str, at: datetime) -> Any:
            gate.wait(5)
            return super().publishing(run_id, at)

    recorder = FeatureRequestRecorder(Slow(MemoryBackend()), maxsize=1, clock=lambda: NEXT)
    with caplog.at_level(logging.WARNING):
        results = [recorder.submit(row(NEXT, f"u{n}")) for n in range(6)]
    gate.set()
    recorder.close()
    assert not all(results) and "queue full" in caplog.text
