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
