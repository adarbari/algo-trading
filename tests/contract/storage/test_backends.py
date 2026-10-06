"""The storage contract: every backend must pass this exact suite (ADR 0006)."""

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.config.env import data_url
from algotrade.core.model.errors import ConfigurationError, DataValidationError, MissingDataError
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.factory import open_backend
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped, universe_rows

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
TABLE = "rollups/instrument/demo@v1"


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def rows(values: dict[str, float]) -> list[dict[str, object]]:
    return [{"instrument_id": k, "value": v} for k, v in values.items()]


def test_round_trip_and_instrument_filter(backend: Backend) -> None:
    backend.tables.write(TABLE, D1, "r1", stamped(rows({"EQ:A": 1.0, "EQ:B": 2.0}), D1, "r1"))
    out = backend.tables.read(TABLE, D1)
    assert out is not None
    assert list(out["value"]) == [1.0, 2.0]
    only_b = backend.tables.read(TABLE, D1, instruments=["EQ:B"])
    assert only_b is not None
    assert list(only_b["instrument_id"]) == ["EQ:B"]
    assert backend.tables.read(TABLE, D2) is None
    assert backend.tables.dates(TABLE) == [D1]
    assert backend.tables.dates("rollups/instrument/none@v1") == []


def test_point_in_time_selection(backend: Backend) -> None:
    later = T0 + timedelta(hours=5)
    backend.tables.write(TABLE, D1, "r1", stamped(rows({"EQ:A": 1.0}), D1, "r1", T0))
    backend.tables.write(TABLE, D1, "r2", stamped(rows({"EQ:A": 9.0}), D1, "r2", later))
    latest = backend.tables.read(TABLE, D1)
    as_of_t0 = backend.tables.read(TABLE, D1, as_of=T0)
    assert latest is not None and as_of_t0 is not None
    assert list(latest["value"]) == [9.0]
    assert list(as_of_t0["value"]) == [1.0]
    assert backend.tables.read(TABLE, D1, as_of=T0 - timedelta(seconds=1)) is None


def test_rewriting_a_run_is_idempotent(backend: Backend) -> None:
    backend.tables.write(TABLE, D1, "r1", stamped(rows({"EQ:A": 1.0}), D1, "r1"))
    backend.tables.write(TABLE, D1, "r1", stamped(rows({"EQ:A": 2.0}), D1, "r1"))
    out = backend.tables.read(TABLE, D1)
    assert out is not None
    assert list(out["value"]) == [2.0]


def test_raw_store(backend: Backend) -> None:
    backend.raw.put("src", "ds", D1, "r1", "SPY", b'{"a": 1}')
    assert backend.raw.get("src", "ds", D1, "r1", "SPY") == b'{"a": 1}'
    assert backend.raw.get("src", "ds", D1, "r1", "QQQ") is None
    backend.raw.put("src", "ds", D2, "r2", "SPY", b"{}")
    assert backend.raw.purge_before(D2) == 1
    assert backend.raw.get("src", "ds", D1, "r1", "SPY") is None
    assert backend.raw.get("src", "ds", D2, "r2", "SPY") == b"{}"


def test_raw_purge_per_source(backend: Backend) -> None:
    assert backend.raw.sources() == []
    for source in ("a", "b"):
        backend.raw.put(source, "ds", D1, "r1", "SPY", b"{}")
        backend.raw.put(source, "ds", D2, "r2", "SPY", b"{}")
    assert backend.raw.sources() == ["a", "b"]
    assert backend.raw.purge_before(D2, source="a") == 1
    assert backend.raw.get("a", "ds", D1, "r1", "SPY") is None
    assert backend.raw.get("a", "ds", D2, "r2", "SPY") == b"{}"
    assert backend.raw.get("b", "ds", D1, "r1", "SPY") == b"{}"  # other sources untouched
    assert backend.raw.purge_before(D2, source="missing") == 0
    assert backend.raw.purge_before(D2) == 1  # every source: only b's old response is left


def test_staging_store(backend: Backend) -> None:
    assert not backend.staging.exists("r1")
    backend.staging.put("r1", "chains/x", "E", pd.DataFrame({"v": []}))
    assert backend.staging.exists("r1")  # an empty frame is still staged
    backend.staging.put("r1", "chains/x", "B", pd.DataFrame({"v": [2]}))
    backend.staging.put("r1", "chains/x", "A", pd.DataFrame({"v": [1]}))
    assert backend.staging.keys("r1", "chains/x") == ["A", "B", "E"]
    collected = backend.staging.collect("r1", "chains/x")
    assert collected is not None
    assert list(collected["v"]) == [1, 2]
    backend.staging.clear("r1")
    assert not backend.staging.exists("r1")
    assert backend.staging.keys("r1", "chains/x") == []
    assert backend.staging.collect("r1", "chains/x") is None
    backend.staging.clear("r1")  # nothing left: a no-op


def test_staging_purge_keeps_recent_and_unrecognised_runs(backend: Backend) -> None:
    old, recent = new_run_id("option_chains", D1, T0), new_run_id("option_chains", D2, T0)
    for run_id in (old, recent, "r1"):
        backend.staging.put(run_id, "chains/x", "A", pd.DataFrame({"v": [1]}))
    assert backend.staging.purge_before(D2) == 1
    assert backend.staging.keys(old, "chains/x") == []
    assert backend.staging.keys(recent, "chains/x") == ["A"]
    assert backend.staging.keys("r1", "chains/x") == ["A"]
    assert backend.staging.purge_before(D2) == 0


def test_run_store(backend: Backend) -> None:
    assert backend.runs.find("job") == []
    record = RunRecord(new_run_id("job", D1, T0), "job", D1, T0, items={"EQ:A": "OK"})
    backend.runs.save(record)
    loaded = backend.runs.load(record.run_id)
    assert loaded is not None
    assert loaded.items == {"EQ:A": "OK"}
    assert loaded.status is RunStatus.RUNNING
    later = RunRecord("job-2", "job", D2, T0 + timedelta(1), RunStatus.COMPLETE, T0 + timedelta(1))
    backend.runs.save(later)
    assert [r.run_id for r in backend.runs.find("job")] == [record.run_id, "job-2"]
    assert [r.run_id for r in backend.runs.find("job", D2)] == ["job-2"]
    assert backend.runs.load("missing") is None


def test_writer_validates_and_reader_requires(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    good = stamped(universe_rows(["A"]), D1, "r1")
    writer.write_table("universe", D1, "r1", good)
    assert reader.latest_date("universe") == D1
    assert reader.latest_date("universe", on_or_before=D1 - timedelta(1)) is None
    with pytest.raises(DataValidationError, match="missing columns"):
        writer.write_table("universe", D1, "r1", good.drop(columns=["symbol"]))
    with pytest.raises(DataValidationError, match="duplicate"):
        writer.write_table("universe", D1, "r1", pd.concat([good, good]))
    with pytest.raises(DataValidationError, match="nulls"):
        writer.write_table("universe", D1, "r1", good.assign(source=None))
    with pytest.raises(DataValidationError, match="unknown table"):
        writer.write_table("nonsense", D1, "r1", good)
    with pytest.raises(MissingDataError, match="To fill it: run x"):
        reader.require("universe", D2, "run x")
    with pytest.raises(ConfigurationError, match="must not contain"):
        writer.write_result("a/b", D1, "r1", good)


def test_local_rejects_unsafe_keys(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path)
    with pytest.raises(ValueError, match="invalid storage key"):
        backend.raw.put("s", "d", D1, "../escape", "k", b"")


def test_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(open_backend("memory://"), MemoryBackend)
    local = open_backend(f"file://{tmp_path}")
    assert isinstance(local, LocalBackend)
    assert local.root == tmp_path
    monkeypatch.setenv("ALGOTRADE_DATA_URL", f"file://{tmp_path}/env")
    env_backend = open_backend(data_url())
    assert isinstance(env_backend, LocalBackend)
    assert env_backend.root == tmp_path / "env"
    with pytest.raises(ConfigurationError, match="unsupported"):
        open_backend("s3://bucket")


def bar_rows(
    day: date, close: float, instruments: tuple[str, ...] = ("EQ:A", "EQ:B")
) -> list[dict[str, object]]:
    ts = pd.Timestamp(day, tz="UTC")
    return [
        {
            "instrument_id": i,
            "ts": ts,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 100.0,
        }
        for i in instruments
    ]


def test_read_range_resolves_each_partition_point_in_time(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    later = T0 + timedelta(hours=1)
    for offset, close in enumerate((10.0, 11.0, 12.0)):
        day = D1 + timedelta(days=offset)
        writer.write_table("bars/1d", day, "r1", stamped(bar_rows(day, close), day, "r1", T0))
    writer.write_table("bars/1d", D2, "r2", stamped(bar_rows(D2, 99.0), D2, "r2", later))
    bars = reader.table_range("bars/1d", D1, D1 + timedelta(days=2))
    assert bars is not None
    assert list(bars[bars.instrument_id == "EQ:A"]["close"]) == [10.0, 99.0, 12.0]
    as_of = reader.table_range("bars/1d", D1, D1 + timedelta(days=2), T0, ["EQ:B"])
    assert as_of is not None
    assert list(as_of["close"]) == [10.0, 11.0, 12.0]
    assert set(as_of["instrument_id"]) == {"EQ:B"}
    assert (
        backend.tables.read_range("bars/1d", D1 - timedelta(days=9), D1 - timedelta(days=1)) is None
    )


def test_bar_validation(backend: Backend) -> None:
    writer = StoreWriter(backend)
    bad = stamped(bar_rows(D1, 10.0), D1, "r1")
    for column, value, message in (
        ("high", 5.0, "high below"),
        ("low", 50.0, "low above"),
        ("open", -1.0, "non-positive"),
        ("volume", -5.0, "negative volume"),
        ("close", float("nan"), "NaN"),
    ):
        with pytest.raises(DataValidationError, match=message):
            writer.write_table("bars/1d", D1, "r1", bad.assign(**{column: value}))
    with pytest.raises(DataValidationError, match="interval"):
        writer.write_table("bars/2d", D1, "r1", bad)


def test_open_ended_table_prefixes(backend: Backend) -> None:
    writer = StoreWriter(backend)
    event = stamped(
        [{"instrument_id": "EQ:A", "ts": pd.Timestamp(D1, tz="UTC"), "kind": "split"}], D1, "r1"
    )
    writer.write_table("events/split", D1, "r1", event)
    with pytest.raises(DataValidationError, match="missing columns"):
        writer.write_table("events/split", D1, "r1", event.drop(columns=["ts"]))
    writer.write_table(
        "catalog/golden_datasets", D1, "r1", stamped([{"instrument_id": "EQ:A"}], D1, "r1")
    )
    with pytest.raises(DataValidationError, match="unknown table"):
        writer.write_table("rollups/instrument/", D1, "r1", event)


def test_events_allow_several_kinds_of_change_per_day(backend: Backend) -> None:
    ts = pd.Timestamp(D1, tz="UTC")
    rows = [
        {"instrument_id": "EQ:META", "ts": ts, "change": "added"},
        {"instrument_id": "EQ:META", "ts": ts, "change": "ticker_changed"},
    ]
    StoreWriter(backend).write_table("events/reference_change", D1, "r1", stamped(rows, D1, "r1"))
    with pytest.raises(DataValidationError, match="duplicate"):
        StoreWriter(backend).write_table(
            "events/reference_change", D1, "r1", stamped(rows[:1] * 2, D1, "r1")
        )


def test_table_names_list_every_written_table(backend: Backend) -> None:
    assert backend.tables.names() == []
    backend.tables.write(TABLE, D1, "r1", stamped(rows({"EQ:A": 1.0}), D1, "r1"))
    backend.tables.write("catalog/demo", D2, "r1", stamped(rows({"EQ:A": 1.0}), D2, "r1"))
    assert StoreReader(backend).table_names() == ["catalog/demo", TABLE]


def test_read_range_prunes_columns_and_keeps_float32(backend: Backend) -> None:
    frame = stamped([{"instrument_id": "EQ:A", "a": 1.5, "b": "x"}], D1, "r1")
    backend.tables.write(TABLE, D1, "r1", frame.astype({"a": "float32"}))
    StoreWriter(backend).write_table(TABLE, D2, "r1", stamped(rows({"EQ:A": 2.0}), D2, "r1"))
    out = StoreReader(backend).table_range(TABLE, D1, D2, columns=["value", "missing"])
    assert out is not None
    assert "a" not in out.columns and "b" not in out.columns and "instrument_id" in out.columns
    assert out["value"].isna().tolist() == [True, False]  # D1 has no such column
    full = backend.tables.read(TABLE, D1)
    assert full is not None and str(full["a"].dtype) == "float32"


def test_size_and_drop_a_table(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    assert writer.table_size(TABLE) == 0 and writer.drop_table(TABLE) == 0
    for day in (D1, D2):
        writer.write_table(TABLE, day, "r1", stamped(rows({"EQ:A": 1.0}), day, "r1"))
    writer.write_table(TABLE, D2, "r2", stamped(rows({"EQ:A": 2.0}), D2, "r2", T0))
    writer.write_table("catalog/demo", D1, "r1", stamped(rows({"EQ:A": 1.0}), D1, "r1"))
    assert writer.table_size(TABLE) > writer.table_size("catalog/demo") > 0
    assert writer.drop_table(TABLE) == 2
    assert reader.dates(TABLE) == [] and reader.table(TABLE, D2) is None
    assert writer.table_size(TABLE) == 0 and reader.table_names() == ["catalog/demo"]
    assert reader.table("catalog/demo", D1) is not None


LIVE = "live/option_quotes"


def live_rows(day: date, strike: float = 100.0) -> list[dict[str, object]]:
    ts = pd.Timestamp(day, tz="UTC")
    row = {"instrument_id": f"OPT:A:{strike}", "underlying_id": "EQ:A", "expiry": day, "ts": ts,
           "right": "C", "strike": strike, "bid": 1.0}  # fmt: skip
    return [row]


def test_purge_before_deletes_only_older_partitions_of_a_table_with_retention(
    backend: Backend,
) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    for day in (D1, D2):
        writer.write_table(LIVE, day, "r1", stamped(live_rows(day), day, "r1"))
        writer.write_table("catalog/demo", day, "r1", stamped(rows({"EQ:A": 1.0}), day, "r1"))
    assert writer.purge_table_before(LIVE, D1) == 0  # the cutoff day itself is kept
    assert writer.purge_table_before(LIVE, D2) == 1
    assert reader.dates(LIVE) == [D2] and reader.table(LIVE, D1) is None
    assert reader.dates("catalog/demo") == [D1, D2]


def test_purging_a_table_without_retention_raises(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    writer.write_table(TABLE, D1, "r1", stamped(rows({"EQ:A": 1.0}), D1, "r1"))
    for table in (TABLE, "chains/option_quotes", "catalog/demo"):
        with pytest.raises(DataValidationError, match="no retention declared"):
            writer.purge_table_before(table, D2)
        with pytest.raises(DataValidationError, match="no retention declared"):
            backend.tables.purge_before(table, D2)
    assert reader.table(TABLE, D1) is not None  # nothing deleted


def test_a_purge_is_committed_whole_and_leaves_pending_runs_alone(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    day0 = D1 - timedelta(1)
    for day in (day0, D1):
        writer.write_table(LIVE, day, "old", stamped(live_rows(day), day, "old"))
    # a run still pending in an old partition (D1) and a new one (D2)
    for day in (D1, D2):
        rows_ = stamped(live_rows(day, 105.0), day, "open")
        writer.write_table(LIVE, day, "open", rows_, pending=True)
    before = reader.visible_seq()
    assert writer.purge_table_before(LIVE, D2) == 1  # day0; D1 holds a pending write
    assert reader.visible_seq() > before  # caches keyed on the sequence invalidate
    assert writer.purge_table_before(LIVE, day0) == 0
    assert reader.visible_seq() == before + 1  # nothing purged: the sequence stays
    assert reader.table(LIVE, day0) is None and day0 not in reader.dates(LIVE)
    assert reader.table_range(LIVE, day0, D2) is not None  # no error, no dangling entries
    assert writer.commit_run("open", T0) == 2  # the pending run commits untouched
    after = reader.table(LIVE, D1)
    assert after is not None and sorted(after["strike"]) == [100.0, 105.0]
    assert reader.table(LIVE, D2) is not None
