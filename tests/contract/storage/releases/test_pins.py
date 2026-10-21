"""Storage contract, pinned reads and retention (ADR 0077 decisions 2, 3, 23): a read given
``upto`` sees the store as of that commit sequence, and a pin (``TableStore.pin``) keeps the
version it saw alive across any number of recommits; without one the version is discarded and
the pinned read raises ``StaleSnapshotError`` (never a mix, never a fresh sequence)."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.run_selection import StaleSnapshotError
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.readers import StoreReader
from tests.helpers.stored_frames import T0, stamped

D0, D1, D2, D3 = date(2026, 9, 1), date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
TABLE = "rollups/instrument/a@v1"
LIVE = "live/option_quotes"
AT = T0 + timedelta(minutes=30)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def commit(backend: Backend, run: str, day: date, value: float, table: str = TABLE) -> int:
    frame = stamped([{"instrument_id": "EQ:A", "value": value}], day, run)
    backend.tables.write(table, day, run, frame, pending=True)
    backend.tables.commit_run(run, AT)
    return backend.tables.visible_seq()


def value(frame: pd.DataFrame | None) -> float:
    assert frame is not None
    return float(frame["value"].iloc[0])


def test_a_pin_keeps_the_pinned_rows_across_three_recommits_of_the_same_run(
    backend: Backend,
) -> None:
    x = commit(backend, "r1", D1, 1.0)
    backend.tables.pin("release-a", x)
    for v in (2.0, 3.0, 4.0):
        commit(backend, "r1", D1, v)  # today the second recommit discards the version at x
    pinned = StoreReader(backend).pinned(x)
    assert value(pinned.table(TABLE, D1)) == 1.0
    assert value(pinned.table_range(TABLE, D1, D1)) == 1.0
    assert value(pinned.read_run(TABLE, D1, "r1")) == 1.0
    assert value(StoreReader(backend).table(TABLE, D1)) == 4.0  # live is unchanged


def test_without_a_pin_the_pinned_read_raises_instead_of_retrying_at_a_fresh_seq(
    backend: Backend,
) -> None:
    x = commit(backend, "r1", D1, 1.0)
    commit(backend, "r1", D1, 2.0)
    commit(backend, "r1", D1, 3.0)
    with pytest.raises(StaleSnapshotError):
        backend.tables.read(TABLE, D1, upto=x)
    with pytest.raises(StaleSnapshotError):
        backend.tables.read_range(TABLE, D1, D1, upto=x)
    with pytest.raises(StaleSnapshotError):
        backend.tables.read_run(TABLE, D1, "r1", upto=x)


def test_unpin_lets_the_next_commit_discard_the_version(backend: Backend) -> None:
    x = commit(backend, "r1", D1, 1.0)
    backend.tables.pin("release-a", x)
    commit(backend, "r1", D1, 2.0)
    commit(backend, "r1", D1, 3.0)
    assert value(backend.tables.read(TABLE, D1, upto=x)) == 1.0
    backend.tables.unpin("release-a")
    assert backend.tables.pins() == {}
    commit(backend, "r1", D1, 4.0)
    with pytest.raises(StaleSnapshotError):
        backend.tables.read(TABLE, D1, upto=x)


def test_each_pin_keeps_its_own_version_and_an_unpinned_one_between_is_stale(
    backend: Backend,
) -> None:
    a = commit(backend, "r1", D1, 1.0)
    backend.tables.pin("a", a)
    between = commit(backend, "r1", D1, 2.0)
    b = commit(backend, "r1", D1, 3.0)
    backend.tables.pin("b", b)
    for v in (4.0, 5.0, 6.0):
        commit(backend, "r1", D1, v)
    assert backend.tables.pins() == {"a": a, "b": b}
    assert value(backend.tables.read(TABLE, D1, upto=a)) == 1.0
    assert value(backend.tables.read(TABLE, D1, upto=b)) == 3.0
    with pytest.raises(StaleSnapshotError):  # version 2 was discarded: never answered as 1 or 3
        backend.tables.read(TABLE, D1, upto=between)


def test_a_pin_above_the_published_sequence_is_refused(backend: Backend) -> None:
    x = commit(backend, "r1", D1, 1.0)
    with pytest.raises(ValueError, match="above"):
        backend.tables.pin("release-a", x + 1)


def test_pins_are_stored_with_the_data_and_a_pin_is_replaced_by_its_name(tmp_path: Path) -> None:
    first = LocalBackend(tmp_path / "data")
    x = commit(first, "r1", D1, 1.0)
    first.tables.pin("release-a", x)
    second = commit(first, "r1", D1, 2.0)
    first.tables.pin("release-a", second)
    assert LocalBackend(tmp_path / "data").tables.pins() == {"release-a": second}


def test_dates_upto_hides_partitions_with_no_version_at_or_below_the_pin(backend: Backend) -> None:
    x = commit(backend, "r1", D1, 1.0)
    commit(backend, "r2", D2, 2.0)  # a later session
    commit(backend, "r3", D0, 3.0)  # a backfilled older date, committed after the pin
    assert backend.tables.dates(TABLE) == [D0, D1, D2]
    assert backend.tables.dates(TABLE, upto=x) == [D1]
    assert backend.tables.dates(TABLE, upto=x) == [D1]  # memoised: the same answer
    pinned = StoreReader(backend).pinned(x)
    assert pinned.dates(TABLE) == [D1]
    assert pinned.latest_date(TABLE) == D1
    assert pinned.earliest_date(TABLE) == D1
    found = pinned.table_range(TABLE, D0, D3)
    assert found is not None and list(found["session_date"]) == [D1]


def test_partition_seq_upto_gives_the_pinned_stamps_and_omits_later_partitions(
    backend: Backend,
) -> None:
    x = commit(backend, "r1", D1, 1.0)
    backend.tables.pin("release-a", x)
    later = commit(backend, "r1", D1, 2.0)
    commit(backend, "r2", D2, 3.0)
    assert backend.tables.partition_seq(TABLE, D0, D3, upto=x) == {D1: x}
    assert backend.tables.partition_seq(TABLE, D0, D1)[D1] == later
    assert StoreReader(backend).pinned(x).partition_seq(TABLE, D0, D3) == {D1: x}


def test_a_pinned_dates_listing_is_not_memoised_across_a_purge(backend: Backend) -> None:
    row = {"ts": pd.Timestamp(D1, tz="UTC"), "right": "C", "strike": 100.0, "bid": 1.0}
    row |= {"instrument_id": "EQ:A"}
    for day in (D1, D2):
        backend.tables.write(LIVE, day, "r1", stamped([row], day, "r1"), pending=True)
    backend.tables.commit_run("r1", AT)
    x = backend.tables.visible_seq()
    assert backend.tables.dates(LIVE, upto=x) == [D1, D2]
    backend.tables.purge_before(LIVE, D2)
    assert backend.tables.dates(LIVE, upto=x) == [D2]


def test_destructive_operations_bump_the_epoch_and_commits_do_not(backend: Backend) -> None:
    start = backend.tables.destructive_epoch()
    commit(backend, "r1", D1, 1.0)
    commit(backend, "r2", D2, 1.0)
    commit(backend, "r1", D1, 2.0)
    assert backend.tables.destructive_epoch() == start  # recommits and restatements are safe

    assert backend.tables.purge_runs(TABLE, D1, ["r1"]) == 1
    after_runs = backend.tables.destructive_epoch()
    assert after_runs > start

    row = {"ts": pd.Timestamp(D1, tz="UTC"), "right": "C", "strike": 100.0, "bid": 1.0}
    row |= {"instrument_id": "EQ:A"}
    for day in (D1, D2):
        backend.tables.write(LIVE, day, "r9", stamped([row], day, "r9"), pending=True)
    backend.tables.commit_run("r9", AT)
    assert backend.tables.destructive_epoch() == after_runs
    assert backend.tables.purge_before(LIVE, D2) == 1
    after_purge = backend.tables.destructive_epoch()
    assert after_purge > after_runs
    assert backend.tables.purge_before(LIVE, D2) == 0  # nothing deleted: nothing bumped
    assert backend.tables.destructive_epoch() == after_purge

    assert backend.tables.drop(TABLE) > 0
    assert backend.tables.destructive_epoch() > after_purge


def test_compaction_leaves_a_partition_holding_a_pinned_version_alone(backend: Backend) -> None:
    """Compaction collapses a run's older version (a read pinned there would raise); with a pin
    on the partition's store it skips the partition instead, so the release stays readable."""
    ts = pd.Timestamp(D1, tz="UTC")

    def dividend(run: str, amount: float, hour: int) -> int:
        row = {"instrument_id": "EQ:A", "ts": ts, "cash_amount": amount}
        frame = stamped([row], D1, run, T0 + timedelta(hours=hour))
        backend.tables.write("events/dividend", D1, run, frame, pending=True)
        backend.tables.commit_run(run, T0 + timedelta(days=1, hours=hour))
        return backend.tables.visible_seq()

    dividend("r1", 1.0, 0)
    x = dividend("r2", 1.0, 1)
    backend.tables.pin("release-a", x)
    dividend("r2", 1.0, 1)  # r2 recommitted: its entry now keeps the pinned version as prev
    dividend("r3", 1.0, 2)
    report = backend.tables.compact_runs("events/dividend", D1)
    assert report.skipped is not None and "pinned" in report.skipped
    assert backend.tables.read("events/dividend", D1, upto=x) is not None


def test_a_run_first_committed_after_the_pin_is_hidden_from_it_not_stale(backend: Backend) -> None:
    """The run did not exist at X: a read there is not an error, even after the run was
    recommitted so often that its first version is gone (and neither is the table's listing)."""
    x = commit(backend, "r1", D1, 1.0)
    backend.tables.pin("release-a", x)
    for v in (2.0, 3.0, 4.0, 5.0):
        commit(backend, "r2", D1, v)  # a second run of the same partition, born after X
        commit(backend, "r3", D2, v)  # and a partition born after X
    assert value(backend.tables.read(TABLE, D1, upto=x)) == 1.0
    assert backend.tables.read(TABLE, D2, upto=x) is None
    assert backend.tables.dates(TABLE, upto=x) == [D1]
    assert backend.tables.partition_seq(TABLE, D1, D2, upto=x) == {D1: x}
    pinned = StoreReader(backend).pinned(x)
    assert value(pinned.table_range(TABLE, D1, D3)) == 1.0


def test_a_direct_write_bumps_the_epoch_because_it_has_no_sequence(backend: Backend) -> None:
    """A write that is not pending replaces rows in place for every pin: such a release is
    not trusted any more."""
    commit(backend, "r1", D1, 1.0)
    before = backend.tables.destructive_epoch()
    frame = stamped([{"instrument_id": "EQ:A", "value": 7.0}], D2, "direct")
    backend.tables.write(TABLE, D2, "direct", frame)
    assert backend.tables.destructive_epoch() > before


def test_compaction_runs_under_a_pin_when_nothing_was_recommitted_after_it(
    backend: Backend,
) -> None:
    ts = pd.Timestamp(D1, tz="UTC")

    def dividend(run: str, hour: int) -> None:
        row = {"instrument_id": "EQ:A", "ts": ts, "cash_amount": 1.0}
        frame = stamped([row], D1, run, T0 + timedelta(hours=hour))
        backend.tables.write("events/dividend", D1, run, frame, pending=True)
        backend.tables.commit_run(run, T0 + timedelta(days=1, hours=hour))

    for hour, run in enumerate(("r1", "r2", "r3", "r3")):  # r3 recommitted: it keeps a chain
        dividend(run, hour)
    backend.tables.pin("current", backend.tables.visible_seq())  # always present
    report = backend.tables.compact_runs("events/dividend", D1)
    assert report.skipped is None and report.runs_dropped == 1


def test_a_partition_written_empty_is_listed_and_stamped_under_a_pin_as_it_is_live(
    backend: Backend,
) -> None:
    """An empty frame leaves a partition with no run (a source with nothing today): live lists it
    and stamps it 0, so a pinned read must too (the release's session record names the table)."""
    x = commit(backend, "r1", D1, 1.0)
    empty = stamped([{"instrument_id": "EQ:A", "value": 1.0}], D2, "empty").iloc[0:0]
    backend.tables.write(TABLE, D2, "empty", empty)
    assert D2 in backend.tables.dates(TABLE)
    assert D2 in backend.tables.dates(TABLE, upto=x)
    assert backend.tables.partition_seq(TABLE, D2, D2) == {D2: 0}
    assert backend.tables.partition_seq(TABLE, D2, D2, upto=x) == {D2: 0}


def test_a_partition_made_empty_by_a_commit_after_the_pin_is_not_listed_at_it(
    backend: Backend,
) -> None:
    """S+1 arrives with no rows (a source with nothing today) after X: live lists it, the pin
    must not (the release's present / missing would flip after the build)."""
    before = stamped([{"instrument_id": "EQ:A", "value": 1.0}], D1, "e0").iloc[0:0]
    backend.tables.write(TABLE, D1, "e0", before, pending=True)
    backend.tables.commit_run("e0", AT)  # S exists, empty, at X
    x = backend.tables.visible_seq()
    later = stamped([{"instrument_id": "EQ:A", "value": 1.0}], D2, "e1").iloc[0:0]
    backend.tables.write(TABLE, D2, "e1", later, pending=True)
    backend.tables.commit_run("e1", AT)
    assert backend.tables.dates(TABLE) == [D1, D2]
    assert backend.tables.dates(TABLE, upto=x) == [D1]
    assert backend.tables.partition_seq(TABLE, D1, D2, upto=x) == {D1: 0}
    assert backend.tables.dates(TABLE, upto=backend.tables.visible_seq()) == [D1, D2]
