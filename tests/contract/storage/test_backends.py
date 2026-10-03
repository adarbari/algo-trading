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
TABLE = "features/demo@v1"


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
    assert backend.tables.dates("features/none@v1") == []


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
