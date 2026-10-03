"""The storage contract: every backend must pass this exact suite (ADR 0006)."""

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.core.errors import ConfigurationError, DataValidationError, MissingDataError
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.factory import open_backend
from algotrade.storage.interfaces import Backend
from algotrade.storage.readers import StoreReader
from algotrade.storage.runs import RunRecord, RunStatus, new_run_id
from algotrade.storage.writers import StoreWriter
from tests.storage_helpers import T0, stamped, universe_rows

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


def test_staging_store(backend: Backend) -> None:
    backend.staging.put("r1", "chains/x", "B", pd.DataFrame({"v": [2]}))
    backend.staging.put("r1", "chains/x", "A", pd.DataFrame({"v": [1]}))
    backend.staging.put("r1", "chains/x", "E", pd.DataFrame({"v": []}))
    assert backend.staging.keys("r1", "chains/x") == ["A", "B", "E"]
    collected = backend.staging.collect("r1", "chains/x")
    assert collected is not None
    assert list(collected["v"]) == [1, 2]
    backend.staging.clear("r1")
    assert backend.staging.keys("r1", "chains/x") == []
    assert backend.staging.collect("r1", "chains/x") is None


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
    env_backend = open_backend()
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
    bars = reader.bars("1d", D1, D1 + timedelta(days=2))
    assert list(bars[bars.instrument_id == "EQ:A"]["close"]) == [10.0, 99.0, 12.0]
    as_of = reader.bars("1d", D1, D1 + timedelta(days=2), ["EQ:B"], as_of=T0)
    assert list(as_of["close"]) == [10.0, 11.0, 12.0]
    assert set(as_of["instrument_id"]) == {"EQ:B"}
    assert (
        backend.tables.read_range("bars/1d", D1 - timedelta(days=9), D1 - timedelta(days=1)) is None
    )
    with pytest.raises(MissingDataError, match="no bars"):
        reader.bars("5m", D1, D2)


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


def test_instrument_reference_snapshots(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    ref = [
        {
            "instrument_id": "EQ:A",
            "symbol": "A",
            "asset_class": "EQ",
            "security_type": "COMMON_STOCK",
            "multiplier": 1.0,
            "status": "ACTIVE",
        },
        {
            "instrument_id": "FUT:ESZ6",
            "symbol": "ESZ6",
            "asset_class": "FUT",
            "security_type": "FUTURE",
            "multiplier": 50.0,
            "status": "ACTIVE",
            "tick_size": 0.25,
        },
    ]
    writer.write_table("instruments/reference", D1, "r1", stamped(ref, D1, "r1"))
    renamed = [{**ref[0], "symbol": "A2"}]
    writer.write_table("instruments/reference", D2, "r2", stamped(renamed, D2, "r2"))
    assert list(reader.instruments(D1)["symbol"]) == ["A", "ESZ6"]
    assert list(reader.instruments(D2 + timedelta(days=5))["symbol"]) == ["A2"]
    terms = reader.instrument_terms(D1)
    assert terms["FUT:ESZ6"].multiplier == 50.0
    assert terms["FUT:ESZ6"].tick_size == 0.25
    assert terms["EQ:A"].tick_size == 0.01
    with pytest.raises(MissingDataError, match="no snapshot"):
        reader.instruments(D1 - timedelta(days=1))


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


def test_instrument_view_joins_reference_and_session_rollups(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    ref = [
        {
            "instrument_id": i,
            "symbol": i[3:],
            "asset_class": "EQ",
            "security_type": "ETF",
            "multiplier": 1.0,
            "status": "ACTIVE",
        }
        for i in ("EQ:A", "EQ:B")
    ]
    writer.write_table("instruments/reference", D1, "r1", stamped(ref, D1, "r1"))
    liq = [{"instrument_id": "EQ:A", "put_tier": "A"}]
    writer.write_table("rollups/instrument/liq@v1", D2, "r2", stamped(liq, D2, "r2"))
    fields = ["instrument.symbol", "rollup.liq@v1.put_tier", "rollup.other@v1.x"]
    view = reader.instrument_view(D2, fields)
    assert view.reference_snapshot == D1
    assert view.missing == ("rollups/instrument/other@v1",)
    rows = view.frame.set_index("instrument_id")
    assert rows.loc["EQ:A", "rollup.liq@v1.put_tier"] == "A"
    assert pd.isna(rows.loc["EQ:B", "rollup.liq@v1.put_tier"])
    everything = reader.instrument_view(D2)
    assert {"instrument.symbol", "instrument.multiplier"} <= set(everything.frame.columns)
    assert reader.instrument_view(D1, ["rollup.liq@v1.put_tier"]).missing == (
        "rollups/instrument/liq@v1",
    )  # a rollup is read for the session only, never stale


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
    backend.tables.write("bars/1d", D2, "r1", stamped(rows({"EQ:A": 1.0}), D2, "r1"))
    assert StoreReader(backend).table_names() == ["bars/1d", TABLE]


def test_resolver_uses_the_reference_as_of_the_session(backend: Backend) -> None:
    writer, reader = StoreWriter(backend), StoreReader(backend)
    assert reader.resolver(D1).id_for("aapl") == "EQ:AAPL"  # no reference yet: symbol ids
    ref = {"asset_class": "EQ", "security_type": "COMMON_STOCK", "multiplier": 1.0}
    day1 = [
        {**ref, "instrument_id": "EQ:BBG1", "symbol": "FB", "status": "ACTIVE"},
        {**ref, "instrument_id": "EQ:OLDCO", "symbol": "OLDCO", "status": "DELISTED"},
    ]
    day2 = [
        {**ref, "instrument_id": "EQ:BBG1", "symbol": "META", "status": "ACTIVE"},
        {**ref, "instrument_id": "EQ:OLDCO", "symbol": "FB", "status": "DELISTED"},
    ]
    writer.write_table("instruments/reference", D1, "r1", stamped(day1, D1, "r1"))
    writer.write_table("instruments/reference", D2, "r2", stamped(day2, D2, "r2"))
    assert reader.resolver(D1).id_for("FB") == "EQ:BBG1"
    assert reader.resolver(D1 - timedelta(days=30)).snapshot == D1  # backfill: earliest
    later = reader.resolver(D2 + timedelta(days=3))
    assert later.snapshot == D2
    assert later.id_for("META") == "EQ:BBG1"
    assert later.id_for("FB") == "EQ:OLDCO"  # only a delisted row has it now
    assert later.symbol_for("EQ:BBG1") == "META"
    frame, unknown = later.resolve(pd.DataFrame({"symbol": ["meta", "NEW"], "x": [1, 2]}))
    assert list(frame["instrument_id"]) == ["EQ:BBG1", "EQ:NEW"] and unknown == 1
