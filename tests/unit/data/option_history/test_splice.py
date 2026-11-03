"""The splice of the pre-cutover chain groups (ADR 0088 decision 11, F7): a read of a chain group
before the cutover goes to the history root, one from the cutover to the main store, any other
table to the main store; a range spanning the cutover is the two parts; what was read from the root
is logged and makes the licence personal; a read the splice cannot route raises rather than
answering from the main store alone."""

from datetime import date, timedelta

import pytest

from algotrade.data import StoreReader
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.data.option_history.splice import SplicedReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

TABLE = "rollups/instrument/iv30@v1"
OTHER = "rollups/instrument/short_premium@v1"  # not one of the nine
BEFORE = FIRST_CBOE_CHAIN_SESSION - timedelta(days=4)
AFTER = FIRST_CBOE_CHAIN_SESSION + timedelta(days=4)


def _rows(value: float) -> list[dict[str, object]]:
    return [{"instrument_id": "EQ:A", "iv30": value}]


def _world() -> tuple[StoreWriter, StoreWriter, SplicedReader]:
    main, hist = StoreWriter(MemoryBackend()), StoreWriter(MemoryBackend())
    hist.write_table(TABLE, BEFORE, "h", stamped(_rows(0.1), BEFORE, "h"))
    hist.write_table(OTHER, BEFORE, "h2", stamped(_rows(0.5), BEFORE, "h2"))
    main.write_table(TABLE, AFTER, "m", stamped(_rows(0.2), AFTER, "m"))
    main.write_table(OTHER, BEFORE, "m2", stamped(_rows(0.6), BEFORE, "m2"))
    return main, hist, SplicedReader(main.backend, StoreReader(hist.backend))


def test_a_read_goes_to_the_source_that_owns_its_session_and_table() -> None:
    _, _, reader = _world()
    assert not reader.reads  # nothing read yet: no licence
    before = reader.table(TABLE, BEFORE)
    after = reader.table(TABLE, AFTER)
    other = reader.table(OTHER, BEFORE)
    assert before is not None and before["iv30"].iloc[0] == 0.1  # the history root
    assert after is not None and after["iv30"].iloc[0] == 0.2  # the main store
    assert other is not None and other["iv30"].iloc[0] == 0.6  # not a chain group
    assert reader.licence == "personal" and reader.reads == [(TABLE, BEFORE)]


def test_a_range_spanning_the_cutover_is_the_two_parts_and_an_empty_side_is_fine() -> None:
    _, _, reader = _world()
    spanning = reader.table_range(TABLE, BEFORE, AFTER)
    assert spanning is not None and list(spanning["iv30"]) == [0.1, 0.2]
    late = reader.table_range(TABLE, FIRST_CBOE_CHAIN_SESSION, AFTER)
    assert late is not None and list(late["iv30"]) == [0.2]  # no history part
    early = reader.table_range(TABLE, BEFORE - timedelta(days=9), BEFORE - timedelta(days=5))
    assert early is None  # the history side holds nothing there
    assert (TABLE, BEFORE) in reader.reads


def test_the_listing_of_a_table_is_the_history_before_the_cutover_and_the_main_store_after() -> (
    None
):
    _, _, reader = _world()
    assert reader.dates(TABLE) == [BEFORE, AFTER]
    assert reader.dates_in(TABLE, BEFORE, AFTER) == [BEFORE, AFTER]
    assert reader.dates_in(TABLE, BEFORE + timedelta(days=1), AFTER) == [AFTER]
    assert reader.has_partition(TABLE, BEFORE) and not reader.has_partition(
        TABLE, FIRST_CBOE_CHAIN_SESSION
    )
    assert reader.dates(OTHER) == [BEFORE]


def test_a_view_shares_the_log_and_reads_the_splice_cannot_route_raise() -> None:
    _, _, reader = _world()
    assert reader.including("r").reads is reader.reads
    with pytest.raises(NotImplementedError):
        reader.recording()
    with pytest.raises(NotImplementedError):
        reader.pinned(1)
    with pytest.raises(NotImplementedError):
        reader.with_runs_frozen(["job"])
    assert isinstance(BEFORE, date)
