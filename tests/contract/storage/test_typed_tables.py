"""Typed tables (``storage/tables/schemas.py``): every backend casts writes to the declared column
types, rejects uncastable data and undeclared columns, and the local backend stamps the schema
version, writes pruneable row groups and reads files written before the types existed."""

import json
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.backends.arrow import ROW_GROUP_SIZE, TABLE_KEY, VERSION_KEY
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.schemas import SCHEMA_VERSION, spec_for
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def bars(ids: list[str], day: date, run: str = "r1", **extra: object) -> pd.DataFrame:
    rows = [
        {"instrument_id": i, "ts": pd.Timestamp(day, tz="UTC"), "open": 10, "high": 11,
         "low": 9, "close": 10, "volume": 100, **extra}
        for i in ids
    ]  # fmt: skip
    return stamped(rows, day, run)


def reference(**overrides: object) -> pd.DataFrame:
    row = {
        "instrument_id": "EQ:A",
        "symbol": "A",
        "asset_class": "EQUITY",
        "security_type": "COMMON_STOCK",
        "multiplier": 1,
        "status": "ACTIVE",
        "delisted_on": None,
        **overrides,
    }
    return stamped([row], D1, "r1")


def test_writes_are_cast_to_the_declared_types(backend: Backend) -> None:
    backend.tables.write("bars/1d", D1, "r1", bars(["EQ:A"], D1, trades=7))  # ints, int trades
    out = backend.tables.read("bars/1d", D1)
    assert out is not None
    assert out["close"].dtype == np.float64 and out["trades"].dtype == np.float64
    assert str(out["ts"].dtype) == "datetime64[us, UTC]"
    backend.tables.write("instruments/reference", D1, "r1", reference())
    ref = backend.tables.read("instruments/reference", D1)
    assert ref is not None and ref["multiplier"].dtype == np.float64
    assert ref["delisted_on"].isna().all()


def test_uncastable_data_and_undeclared_columns_fail(backend: Backend) -> None:
    with pytest.raises(DataValidationError, match="multiplier: cannot store"):
        backend.tables.write("instruments/reference", D1, "r1", reference(multiplier="one"))
    with pytest.raises(DataValidationError, match="undeclared column 'colour'"):
        backend.tables.write("instruments/reference", D1, "r1", reference(colour="red"))
    with pytest.raises(DataValidationError, match="undeclared columns"):
        StoreWriter(backend).write_table("instruments/reference", D1, "r1", reference(colour="r"))
    with pytest.raises(DataValidationError, match="ts: nulls in a non-nullable column"):
        backend.tables.write("bars/1d", D1, "r1", bars(["EQ:A"], D1).assign(ts=None))
    # Open-ended tables keep producer-defined columns as they come; only the keys are typed.
    event = stamped([{"instrument_id": "EQ:A", "ts": T0, "ratio": 2, "kind": "split"}], D1, "r1")
    backend.tables.write("events/split", D1, "r1", event)
    out = backend.tables.read("events/split", D1)
    assert out is not None and list(out["ratio"]) == [2]


def test_known_from_is_stored_as_a_date_on_events_and_rejected_on_bars(backend: Backend) -> None:
    rows = [{"instrument_id": "EQ:A", "ts": T0, "known_from": pd.Timestamp(2019, 5, 1)}]
    backend.tables.write("events/earnings", D2, "r1", stamped(rows, D2, "r1"))
    out = backend.tables.read("events/earnings", D2)
    assert out is not None and out["known_from"].iloc[0] == date(2019, 5, 1)
    null = [{"instrument_id": "EQ:B", "ts": T0, "known_from": None}]
    with pytest.raises(DataValidationError, match="known_from: nulls"):
        backend.tables.write("events/earnings", D2, "r2", stamped(null, D2, "r2"))
    backend.tables.write("events/split", D2, "r1", stamped(null, D2, "r1"))  # optional there
    with pytest.raises(DataValidationError, match="undeclared column 'known_from'"):
        backend.tables.write("bars/1d", D1, "r1", bars(["EQ:A"], D1, known_from=D1))


def test_every_fixed_table_declares_its_required_columns() -> None:
    for name in ("universe", "chains/option_quotes", "instruments/reference", "bars/1d"):
        spec = spec_for(name)
        assert all(spec.column(c) is not None for c in spec.required), name
        assert not spec.open_ended


# ----------------------------------------------------------------------------- local files


def _file(root: Path, table: str, day: date, run: str) -> Path:
    return root / "tables" / table / f"date={day.isoformat()}" / f"run={run}.parquet"


def test_files_are_stamped_and_written_in_row_groups(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path)
    backend.tables.write("bars/1d", D1, "r1", bars(["EQ:A", "EQ:B"], D1))
    schema = pq.read_schema(_file(tmp_path, "bars/1d", D1, "r1"))
    assert schema.metadata[TABLE_KEY] == b"bars/1d"
    assert schema.metadata[VERSION_KEY] == str(SCHEMA_VERSION).encode()
    assert schema.field("instrument_id").type == pa.large_string()
    assert b"pandas" not in schema.metadata


def test_a_filtered_read_touches_fewer_row_groups(tmp_path: Path) -> None:
    ids = [f"EQ:{i:06d}" for i in range(3 * ROW_GROUP_SIZE)]  # sorted, as producers write
    frame = bars(ids, D1)
    backend = LocalBackend(tmp_path)
    backend.tables.write("bars/1d", D1, "r1", frame)
    path = _file(tmp_path, "bars/1d", D1, "r1")
    meta = pq.ParquetFile(path).metadata
    assert meta.num_row_groups == 3 and meta.row_group(0).column(0).statistics.has_min_max
    assert pq.ParquetFile(path).metadata.row_group(0).num_rows == ROW_GROUP_SIZE
    fragment = next(iter(ds.dataset(path, format="parquet").get_fragments()))
    wanted = ds.field("instrument_id").isin(["EQ:000001", "EQ:000002"])
    assert len(fragment.split_by_row_group(wanted)) == 1  # 1 of 3 row groups read
    out = backend.tables.read("bars/1d", D1, instruments=["EQ:000001", "EQ:000002"])
    assert out is not None and list(out["instrument_id"]) == ["EQ:000001", "EQ:000002"]


def _write_old_style(root: Path, table: str, day: date, run: str, data: pa.Table) -> None:
    """A partition as the backend wrote it before typed schemas (pandas-inferred types)."""
    path = _file(root, table, day, run)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(data, path)
    index = {run: pd.Timestamp(T0).isoformat()}
    (path.parent / "_runs.json").write_text(json.dumps(index))


def test_files_written_before_typed_schemas_still_read(tmp_path: Path) -> None:
    first = pa.Table.from_pandas(bars(["EQ:A"], D1).assign(trades=3), preserve_index=False)
    ids = first.column("instrument_id").cast(pa.string())
    first = first.set_column(0, pa.field("instrument_id", pa.string()), ids)
    assert first.schema.field("trades").type == pa.int64()
    second = pa.Table.from_pandas(bars(["EQ:B"], D2).assign(vwap=None), preserve_index=False)
    assert second.schema.field("instrument_id").type == pa.large_string()
    assert second.schema.field("vwap").type == pa.null()
    _write_old_style(tmp_path, "bars/1d", D1, "old1", first)
    _write_old_style(tmp_path, "bars/1d", D2, "old2", second)
    backend = LocalBackend(tmp_path)
    out = backend.tables.read_range("bars/1d", D1, D2)
    assert out is not None and list(out["instrument_id"]) == ["EQ:A", "EQ:B"]
    assert out["trades"].tolist()[0] == 3.0 and out["vwap"].isna().all()
    one = backend.tables.read("bars/1d", D1, instruments=["EQ:A"])
    assert one is not None and one["close"].tolist() == [10.0]


def test_unstorable_frames_fail_and_unknown_tables_pass_through(backend: Backend) -> None:
    mixed = stamped(
        [{"instrument_id": "EQ:A", "v": 1}, {"instrument_id": "EQ:B", "v": "x"}], D1, "r"
    )
    with pytest.raises(DataValidationError, match="not storable as columns"):
        backend.tables.write("catalog/demo", D1, "r", mixed)
    backend.tables.write("scratch", D1, "r", stamped([{"instrument_id": "EQ:A"}], D1, "r"))
    assert backend.tables.names() == ["scratch"]
