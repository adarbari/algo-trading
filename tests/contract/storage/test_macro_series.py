"""``macro/series`` (ADR 0048) on every backend: typed round trip, ``as_of``, idempotent and
merging runs on (``instrument_id``, ``obs_date``, ``vintage_date``), schema rejection."""

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.schemas import MACRO_SERIES, spec_for
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped

TABLE = MACRO_SERIES.name
DAY = date(2026, 10, 6)
LATER = T0 + timedelta(days=1)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def vintage(obs: str, vintage: str, value: float | None, kind: str = "alfred") -> dict[str, object]:
    return {
        "instrument_id": "MACRO:UNRATE",
        "series": "UNRATE",
        "obs_date": date.fromisoformat(obs),
        "vintage_date": date.fromisoformat(vintage),
        "value": value,
        "vintage_kind": kind,
    }


def write(backend: Backend, run: str, rows: list[dict[str, object]], at: object = T0) -> None:
    frame = stamped(rows, DAY, run, at, "fred")  # type: ignore[arg-type]
    StoreWriter(backend).write_table(TABLE, DAY, run, frame)


def test_the_table_is_reference_grain_and_merges_on_its_vintage_key() -> None:
    spec = spec_for(TABLE)
    assert (spec.grain, spec.runs) == ("reference", "merge")
    assert spec.key == ("instrument_id", "obs_date", "vintage_date")
    nullable = {c.name: c.nullable for c in spec.columns}
    assert not nullable["obs_date"] and not nullable["vintage_date"]
    assert not nullable["vintage_kind"] and nullable["value"]


def test_round_trip_keeps_types_and_null_values(backend: Backend) -> None:
    write(
        backend,
        "r1",
        [vintage("2008-01-01", "2008-02-01", 5.0), vintage("2008-02-01", "2008-03-07", None)],
    )
    back = backend.tables.read(TABLE, DAY)
    assert back is not None and len(back) == 2
    assert list(pd.to_datetime(back["obs_date"]).dt.date) == [date(2008, 1, 1), date(2008, 2, 1)]
    assert back["value"].isna().tolist() == [False, True]
    assert str(back["value"].dtype) == "float64"


def test_rewriting_a_run_is_idempotent_and_runs_merge_per_vintage(backend: Backend) -> None:
    first = [vintage("2008-01-01", "2008-02-01", 5.0)]
    write(backend, "r1", first)
    write(backend, "r1", first)  # the same run again replaces it
    revision = [vintage("2008-01-01", "2008-03-07", 5.1), vintage("2008-01-01", "2008-02-01", 5.0)]
    write(backend, "r2", revision, LATER)
    merged = backend.tables.read(TABLE, DAY)
    assert merged is not None and len(merged) == 2  # two vintages, one row each
    assert sorted(merged["value"]) == [5.0, 5.1]
    assert list(merged.sort_values("vintage_date")["run_id"]) == ["r2", "r2"]


def test_as_of_pins_what_the_store_held(backend: Backend) -> None:
    write(backend, "r1", [vintage("2008-01-01", "2008-02-01", 5.0)])
    write(backend, "r2", [vintage("2008-01-01", "2008-03-07", 5.1)], LATER)
    before = backend.tables.read(TABLE, DAY, as_of=LATER - timedelta(seconds=1))
    assert before is not None and list(before["value"]) == [5.0]
    assert backend.tables.read(TABLE, DAY, as_of=T0 - timedelta(seconds=1)) is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"vintage_kind": "guessed"}, "vintage_kind must be one of"),
        ({"vintage_kind": None}, "vintage_kind must be one of"),
        ({"obs_date": "not a date"}, "obs_date"),
        ({"note": "x"}, "undeclared columns"),
    ],
)
def test_bad_rows_are_rejected(backend: Backend, change: dict[str, object], message: str) -> None:
    with pytest.raises(DataValidationError, match=message):
        write(backend, "r1", [{**vintage("2008-01-01", "2008-02-01", 5.0), **change}])


def test_a_key_repeated_within_a_run_is_rejected(backend: Backend) -> None:
    row = vintage("2008-01-01", "2008-02-01", 5.0)
    with pytest.raises(DataValidationError, match="duplicate rows"):
        write(backend, "r1", [row, {**row, "value": 5.1}])
