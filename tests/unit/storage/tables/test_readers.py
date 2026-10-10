"""``RecordingReader`` (ADR 0063): the reads a day makes are logged against that day, including
reads that found nothing; reads outside ``attribute`` are not."""

from datetime import date, timedelta

import pytest

from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import ReadRecord, RecordingReader, StoreReader, dates_digest
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
A, B = "rollups/instrument/a@v1", "rollups/instrument/b@v1"


def publish(backend: MemoryBackend, run: str, table: str, *days: date) -> None:
    writer = StoreWriter(backend)
    for day in days:
        frame = stamped([{"instrument_id": "EQ:A", "value": 1.0}], day, run)
        writer.write_table(table, day, run, frame, pending=True)
    backend.tables.commit_run(run, T0 + timedelta(minutes=5))


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
        ReadRecord(A, D2, D2, "rows"),
        ReadRecord(B, D2, D2, "rows"),
        ReadRecord(A, D1, D2, "rows"),
        ReadRecord(A, D1, D1, "rows"),
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
    assert reader.reads(D1) == (ReadRecord(A, D1, D1, "rows"),)


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
    assert reader.reads(D2) == (ReadRecord(A, D2, D2, "rows"), ReadRecord(A, D1, D1, "rows"))
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
    assert recording.reads(D1) == (ReadRecord(A, D1, D1, "rows"),)
