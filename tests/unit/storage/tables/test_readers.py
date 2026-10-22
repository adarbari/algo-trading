"""``RecordingReader`` (ADR 0063): the reads a day makes are logged against that day, including
reads that found nothing; reads outside ``attribute`` are not."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import (
    ReadRecord,
    RecordingReader,
    RollingRead,
    StoreReader,
    dates_digest,
)
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, publish, stamped

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
A, B = "rollups/instrument/a@v1", "rollups/instrument/b@v1"


def test_reads_are_logged_per_attributed_day_found_or_not() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1, D2)
    reader = RecordingReader(backend)
    with reader.attribute(D2):
        assert reader.table(A, D2) is not None
        assert reader.table(B, D2) is None  # found nothing: still recorded
        assert reader.table_range(A, D1, D2) is not None
        reader.require(A, D1, "hint")
    assert reader.reads(D2) == (
        ReadRecord(A, D2, D2, "rows", dates_digest([D2])),
        ReadRecord(B, D2, D2, "rows", dates_digest([])),  # none found: a partition that
        ReadRecord(A, D1, D2, "rows", dates_digest([D1, D2])),  # appears later is noticed
        ReadRecord(A, D1, D1, "rows", dates_digest([D1])),
    )
    assert reader.reads(D1) == () and reader.attributed_days() == [D2]


def test_dates_and_latest_date_log_the_listing_the_caller_used() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1, D2)
    reader = RecordingReader(backend)
    with reader.attribute(D2):
        assert reader.dates(A) == [D1, D2]
        assert reader.latest_date(A, D2) == D2
        assert reader.dates(B) == []
    digest = dates_digest([D1, D2])
    assert reader.reads(D2) == (
        ReadRecord(A, D1, D2, "dates", digest),
        ReadRecord(B, D2, D2, "dates", dates_digest([])),
    )


def test_a_listing_that_includes_later_dates_is_recorded_as_a_read_of_them() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1, D2, D3)
    reader = RecordingReader(backend)
    with reader.attribute(D2):
        assert reader.dates(A) == [D1, D2, D3]
        assert reader.latest_date(A) == D3  # no bound: the future was used
        assert reader.latest_date(A, D2) == D2  # bounded at the day: only up to it
    assert reader.reads(D2) == (
        ReadRecord(A, D1, D3, "dates", dates_digest([D1, D2, D3])),
        ReadRecord(A, D1, D2, "dates", dates_digest([D1, D2])),
    )


def test_reads_outside_a_block_are_not_logged_and_blocks_do_not_nest() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    reader = RecordingReader(backend)
    reader.table(A, D1)
    reader.dates(A)
    assert reader.attributed_days() == [] and reader.inputs_seq(D1) is None
    with reader.attribute(D1):
        with pytest.raises(RuntimeError, match="does not nest"), reader.attribute(D2):
            pass
        reader.table(A, D1)
    reader.table(A, D1)  # the block ended: not logged again
    assert reader.reads(D1) == (ReadRecord(A, D1, D1, "rows", dates_digest([D1])),)


def test_inputs_seq_is_the_sequence_at_the_first_read_of_the_day() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    reader = RecordingReader(backend)
    first = backend.tables.visible_seq()
    with reader.attribute(D1):
        reader.table(A, D1)
        publish(backend, "r2", A, D1)  # a commit mid-day
        reader.table(A, D1)
    with reader.attribute(D2):
        reader.table(A, D2)
    assert reader.inputs_seq(D1) == first
    assert reader.inputs_seq(D2) == backend.tables.visible_seq() > first


def test_including_keeps_recording_into_the_same_log() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    writer = StoreWriter(backend)
    writer.write_table(
        A, D2, "mine", stamped([{"instrument_id": "EQ:A", "value": 2.0}], D2, "mine"), pending=True
    )
    reader = RecordingReader(backend)
    own = reader.including("mine")
    assert isinstance(own, RecordingReader) and own.own_run == "mine"
    with reader.attribute(D2):
        assert own.table(A, D2) is not None  # sees its own pending write
        reader.table(A, D1)
    assert reader.reads(D2) == (
        ReadRecord(A, D2, D2, "rows", dates_digest([])),  # its own write is pending: not listed
        ReadRecord(A, D1, D1, "rows", dates_digest([D1])),
    )
    assert own.reads(D2) == reader.reads(D2)


def test_it_is_a_store_reader_and_serves_partition_stamps() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    reader = RecordingReader(backend)
    assert isinstance(reader, StoreReader)
    assert reader.partition_seq(A, D1, D3) == {D1: backend.tables.visible_seq()}


def test_a_store_reader_makes_a_recording_one_of_its_own_view() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    plain = StoreReader(backend, "mine")
    recording = plain.recording()
    assert isinstance(recording, RecordingReader) and recording.own_run == "mine"
    with recording.attribute(D1):
        recording.table(A, D1)
    assert recording.reads(D1) == (ReadRecord(A, D1, D1, "rows", dates_digest([D1])),)


def test_a_filtered_read_records_the_committed_partitions_the_store_lists() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    reader = RecordingReader(backend)
    with reader.attribute(D1):
        reader.table(A, D1, instruments=["EQ:A"])
        reader.table_range(A, D1, D1, T0 + timedelta(days=9))
    assert reader.reads(D1) == (ReadRecord(A, D1, D1, "rows", dates_digest([D1])),)


def test_capture_logs_like_a_direct_read_and_replay_hands_it_to_another_reader() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    reader, other = RecordingReader(backend), RecordingReader(backend)
    start = backend.tables.visible_seq()
    with reader.attribute(D1), reader.capture(D1) as got:
        reader.table(A, D1)
    assert got.seq == start and got.records == reader.reads(D1) and len(got.records) == 1
    assert reader.inputs_seq(D1) == start
    with other.attribute(D1):
        other.replay(D1, got)
    assert other.reads(D1) == reader.reads(D1) and other.inputs_seq(D1) == start


def test_a_capture_that_reads_nothing_leaves_the_day_unregistered() -> None:
    reader = RecordingReader(MemoryBackend())
    with reader.attribute(D1), reader.capture(D1) as got:
        pass
    assert got.records == () and reader.reads(D1) == () and reader.inputs_seq(D1) is None
    assert reader.attributed_days() == []
    reader.replay(D1, got)  # nothing to hand over: still nothing registered
    assert reader.attributed_days() == []


def test_replay_takes_the_earlier_sequence_so_a_later_commit_is_never_unchanged() -> None:
    """A partition committed after the capture started must not read as unchanged: the day's
    sequence is the earlier of its own and the capture's (ADR 0063)."""
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    source, reader = RecordingReader(backend), RecordingReader(backend)
    with source.attribute(D1), source.capture(D1) as got:
        source.table(A, D1)
    early = got.seq
    publish(backend, "r2", A, D1)  # a commit lands between the two edges
    with reader.attribute(D1):
        reader.table(A, D1)  # the second edge's own read of the day: a newer sequence
        assert reader.inputs_seq(D1) > early
        reader.replay(D1, got)
    assert reader.inputs_seq(D1) == early


def test_capture_outside_the_attributed_day_is_refused() -> None:
    reader = RecordingReader(MemoryBackend())
    with pytest.raises(RuntimeError, match="capture"), reader.capture(D1):
        pass
    with reader.attribute(D2), pytest.raises(RuntimeError, match="capture"), reader.capture(D1):
        pass


def test_a_capture_that_raises_keeps_its_partial_reads_and_a_day_with_reads_its_sequence() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    reader = RecordingReader(backend)
    first = backend.tables.visible_seq()
    with reader.attribute(D1):
        reader.table(A, D1)  # the day's own first read
        publish(backend, "r2", A, D1)
        with pytest.raises(ValueError, match="boom"), reader.capture(D1):
            reader.table(A, D2)
            raise ValueError("boom")
        assert len(reader.reads(D1)) == 2  # the partial read stays logged, as before
    assert reader.inputs_seq(D1) == first  # the earlier sequence of the day is kept
    with reader.attribute(D2), pytest.raises(ValueError, match="boom"), reader.capture(D2):
        reader.table(A, D2)
        raise ValueError("boom")
    assert reader.inputs_seq(D2) is not None and len(reader.reads(D2)) == 1


def test_a_pinned_reader_reads_as_of_its_sequence_and_keys_by_the_pin() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    x = backend.tables.visible_seq()
    publish(backend, "r2", A, D2)
    live = StoreReader(backend)
    pinned = live.pinned(x)
    assert live.version() == ("live", backend.tables.visible_seq())
    assert pinned.version() == ("pin", x)
    publish(backend, "r3", A, D3)
    assert pinned.version() == ("pin", x)  # stable while the store moves on
    assert pinned.dates(A) == [D1] and pinned.latest_date(A) == D1
    assert pinned.table(A, D2) is None
    assert pinned.including("r9").version() == ("pin", x)
    assert pinned.recording().version() == ("pin", x)


def test_a_pinned_recording_reader_logs_the_pinned_partitions() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    x = backend.tables.visible_seq()
    publish(backend, "r2", A, D2)
    reader = RecordingReader(backend).pinned(x)
    with reader.attribute(D2):
        assert reader.table_range(A, D1, D3) is not None
    assert reader.reads(D2) == (ReadRecord(A, D1, D3, "rows", dates_digest([D1])),)


def test_a_rolling_range_read_equals_the_plain_one_and_logs_the_whole_range() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1, D2)
    reader = RecordingReader(backend)
    memo = RollingRead(A, ("value",))
    plain = StoreReader(backend)
    with reader.attribute(D3):
        first = reader.table_range_rolling(memo, D1, D2)
    publish(backend, "r2", A, D3)  # a new partition after the window: appended
    with reader.attribute(D3):
        second = reader.table_range_rolling(memo, D2, D3)  # the window moved: D1 dropped
    pd.testing.assert_frame_equal(first, plain.table_range(A, D1, D2, None, None, ["value"]))
    pd.testing.assert_frame_equal(second, plain.table_range(A, D2, D3, None, None, ["value"]))
    assert reader.reads(D3) == (
        ReadRecord(A, D1, D2, "rows", dates_digest([D1, D2])),
        ReadRecord(A, D2, D3, "rows", dates_digest([D2, D3])),
    )
    publish(backend, "r3", A, D2)  # a kept partition restated: the range is read whole again
    pd.testing.assert_frame_equal(
        reader.table_range_rolling(memo, D2, D3),
        plain.table_range(A, D2, D3, None, None, ["value"]),
    )
    assert len(plain.table_range(A, D2, D3, None, None, ["value"])) == 2


def _rolled(reader: StoreReader, memo: RollingRead, a: date, b: date) -> pd.DataFrame | None:
    return reader.table_range_rolling(memo, a, b)


def _same(reader: StoreReader, memo: RollingRead, a: date, b: date) -> None:
    want = reader.table_range(A, a, b, None, None, ["value"])
    pd.testing.assert_frame_equal(_rolled(reader, memo, a, b), want)  # type: ignore[arg-type]


def _publish_instrument(backend: LocalBackend, run: str, iid: str, day: date) -> None:
    frame = stamped([{"instrument_id": iid, "value": 1.0}], day, run)
    StoreWriter(backend).write_table(A, day, run, frame, pending=True)
    backend.tables.commit_run(run, T0 + timedelta(minutes=5))


def test_a_rolling_read_sees_a_purged_run_a_pinned_one_and_a_direct_write(tmp_path: Path) -> None:
    """No partition stamp moves on a purge of a non-top run or a direct write (``epoch`` does)."""
    backend = LocalBackend(tmp_path)
    publish(backend, "r0", A, D1)
    for n, pinned in enumerate((False, True, False)):
        day = date(2026, 10, 2 + n)
        _publish_instrument(backend, f"a{n}", "EQ:A", day)
        _publish_instrument(backend, f"b{n}", "EQ:B", day)  # the day holds two runs' rows
        reader = StoreReader(backend)
        reader = reader.pinned(backend.tables.visible_seq()) if pinned else reader
        memo = RollingRead(A, ("value",))
        _same(reader, memo, D1, day)
        if n < 2:
            backend.tables.purge_runs(A, day, [f"a{n}"])  # a non-top run: its rows go
        else:
            frame = stamped([{"instrument_id": "EQ:C", "value": 7.0}], day, "direct")
            StoreWriter(backend).write_table(A, day, "direct", frame)  # no sequence
        _same(reader, memo, D1, day)


def _gappy(backend: MemoryBackend | LocalBackend) -> list[date]:
    """A table with gaps, a day committed after the first pin, and one far outside any window."""
    days = [date(2026, 1, 5), date(2026, 9, 1), date(2026, 9, 3), D1, D3]
    for n, day in enumerate(days):
        publish(backend, f"g{n}", A, day)
    return days


def _no_listing(reader: StoreReader, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> list[date]:
        raise AssertionError("dates_in listed the table")

    monkeypatch.setattr(reader._backend.tables, "dates", refuse)


@pytest.mark.parametrize("kind", ["memory", "local"])
def test_dates_in_equals_the_listing_restricted_to_the_span_without_listing(
    kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = MemoryBackend() if kind == "memory" else LocalBackend(tmp_path)
    days = _gappy(backend)
    reader = StoreReader(backend)
    spans = [(date(2026, 8, 20), D3), (D2, D2), (D1, D1), (date(2026, 1, 1), date(2026, 1, 31))]
    expected = {s: [d for d in reader.dates(A) if s[0] <= d <= s[1]] for s in spans}
    _no_listing(reader, monkeypatch)
    for (start, end), want in expected.items():
        assert reader.dates_in(A, start, end) == want
    assert reader.dates_in(A, date(2026, 8, 20), D3) == [days[1], days[2], D1, D3]
    assert reader.dates_in(A, D3, D1) == []  # an empty span


def test_dates_in_under_a_pin_sees_the_pinned_view_only(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1)
    x = backend.tables.visible_seq()
    publish(backend, "r2", A, D2)
    publish(backend, "r3", A, date(2026, 9, 20))  # backfilled after the pin
    live = StoreReader(backend)
    pinned = live.pinned(x)
    span = (date(2026, 9, 1), D3)
    assert live.dates_in(A, *span) == [date(2026, 9, 20), D1, D2]
    assert (
        pinned.dates_in(A, *span) == [D1] == [d for d in pinned.dates(A) if span[0] <= d <= span[1]]
    )
    _no_listing(pinned, monkeypatch)
    assert pinned.dates_in(A, *span) == [D1]


def test_a_span_over_the_probe_cap_lists_once_and_gives_the_same_days() -> None:
    backend = MemoryBackend()
    _gappy(backend)
    reader = StoreReader(backend)
    start, end = date(2024, 1, 1), D3
    assert (end - start).days > 366
    assert reader.dates_in(A, start, end) == [d for d in reader.dates(A) if start <= d <= end]


def test_a_recording_reader_logs_a_windowed_listing_as_a_listing() -> None:
    backend = MemoryBackend()
    publish(backend, "r1", A, D1, D2)
    reader = RecordingReader(backend)
    with reader.attribute(D2):
        assert reader.dates_in(A, D1, D2) == [D1, D2]
    assert [r.kind for r in reader.reads(D2)] == ["dates"]
