"""The rollup framework: declaration validation, column typing, input loaders, and the runner
(point in time per session; a backfill equals per-session compute, across chunks)."""

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.features.framework import inputs
from algotrade.features.framework.columns import conform
from algotrade.features.framework.declaration import Input, Inputs, Rollup
from algotrade.features.framework.runner import (
    by_key,
    compute_one,
    compute_sessions,
    rollup_params,
)
from algotrade.features.registry import ROLLUPS
from algotrade.storage.configs.files import MemoryConfigStore
from tests.helpers.rollup_store import END, series, store, write_bars


@dataclass(frozen=True)
class Window:
    sessions: int = 3


def seen(frames: Inputs, session: date, p: Window) -> pd.DataFrame:
    """For each instrument: how many bars it saw, and the first / last session among them."""
    bars = frames["bars/1d"]
    assert bars is not None
    grouped = bars.groupby("instrument_id")["session_date"]
    return pd.DataFrame(
        {
            "instrument_id": grouped.size().index,
            "bars": grouped.size().to_numpy(),
            "first": grouped.min().to_numpy(),
            "last": grouped.max().to_numpy(),
        }
    )


COUNTING = Rollup(
    "seen",
    1,
    "test rollup",
    (Input("bars/1d", lookback=lambda p: p.sessions - 1),),
    {"bars": "int", "first": "date", "last": "date"},
    seen,
    Window(),
)


def _rollup(**changes: Any) -> Rollup:
    base: dict[str, Any] = {
        "name": "x",
        "version": 1,
        "description": "",
        "inputs": (Input("bars/1d"),),
        "columns": {"a": "float"},
        "compute": seen,
    }
    return Rollup(**{**base, **changes})


# ----------------------------------------------------------------------------- declaration


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"name": "Bad-Name"}, "name must match"),
        ({"version": 0}, "version"),
        ({"inputs": ()}, "at least one input"),
        ({"inputs": (Input("bars/1d"), Input("bars/1d"))}, "twice"),
        ({"columns": {}}, "output column"),
        ({"columns": {"a": "decimal"}}, "types must be"),
        ({"columns": {"run_id": "str"}}, "reserved"),
        ({"params": {"a": 1}}, "dataclass"),
    ],
)
def test_declaration_is_validated(changes: dict[str, Any], problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        _rollup(**changes)


def test_key_table_and_lookback() -> None:
    assert (COUNTING.key, COUNTING.table) == ("seen@v1", "rollups/instrument/seen@v1")
    assert COUNTING.inputs[0].sessions_back(Window(5)) == 4
    with pytest.raises(ValueError, match="lookback"):
        Input("bars/1d", lookback=-1).sessions_back(None)


# ----------------------------------------------------------------------------- columns


def test_conform_types_by_declaration_and_round_trips() -> None:
    columns = {"f": "float", "i": "int", "b": "bool", "s": "str", "d": "date", "gone": "date"}
    frame = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B"],
            "f": [1, None],
            "i": [2.0, None],
            "b": [True, None],
            "s": ["x", None],
            "d": [pd.Timestamp("2026-10-02 20:15", tz="UTC"), None],
        }
    )
    out = conform("rollups/instrument/t@v1", frame, columns)
    assert list(out.columns) == ["instrument_id", *columns]
    assert [str(out[c].dtype) for c in columns] == [
        "float64",
        "int64[pyarrow]",
        "bool[pyarrow]",
        "string",
        "date32[day][pyarrow]",
        "date32[day][pyarrow]",
    ]
    assert out["d"].iloc[0] == date(2026, 10, 2) and out["gone"].isna().all()
    writer, reader = store()
    stamped = out.assign(session_date=END, knowledge_ts=pd.Timestamp(END, tz="UTC"))
    writer.write_table("rollups/instrument/t@v1", END, "r", stamped.assign(source="t", run_id="r"))
    back = reader.table("rollups/instrument/t@v1", END)
    assert back is not None and back["i"].iloc[0] == 2 and back["gone"].isna().all()


def test_conform_rejects_undeclared_and_unfit_columns() -> None:
    with pytest.raises(DataValidationError, match="undeclared"):
        conform("t", pd.DataFrame({"instrument_id": ["A"], "x": [1]}), {"a": "float"})
    with pytest.raises(DataValidationError, match="instrument_id"):
        conform("t", pd.DataFrame({"a": [1.0]}), {"a": "float"})
    with pytest.raises(DataValidationError, match="not a int"):
        conform("t", pd.DataFrame({"instrument_id": ["A"], "a": [1.5]}), {"a": "int"})


# ----------------------------------------------------------------------------- inputs


def test_loaders() -> None:
    assert inputs.sessions_before(date(2026, 10, 5), 1) == date(2026, 10, 2)  # Mon -> Fri
    assert inputs.sessions_before(date(2026, 10, 4), 0) == date(2026, 10, 2)  # Sunday
    _, reader = store()
    chains = inputs.load_input(reader, "chains/status", [END], 0)
    assert chains.at(END, 0) is None
    with pytest.raises(ValueError, match="lookback"):
        chains.at(END, 1)
    assert inputs.load_input(reader, "events/earnings", [END], 0).at(END, 0) is None
    assert inputs.load_input(reader, "bars/1d", [END], 3).at(END, 3) is None
    with pytest.raises(KeyError, match="no input loader"):
        inputs.load_input(reader, "bars/5m", [END], 0)


# ----------------------------------------------------------------------------- runner


def test_each_session_sees_only_its_window() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(10)})
    for result in compute_sessions(reader, COUNTING, days[3:]):
        assert result.frame is not None
        a = result.frame.iloc[0]
        i = days.index(result.session)
        assert (a["bars"], a["first"], a["last"]) == (3, days[i - 2], result.session)


def test_backfill_equals_per_session_compute_across_chunks() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(12), "EQ:B": series(8, seed=4)})
    whole = list(compute_sessions(reader, COUNTING, days, chunk=5))
    assert [r.session for r in whole] == days
    for result in whole:
        alone = compute_one(reader, COUNTING, result.session)
        assert result.frame is not None and alone.frame is not None
        pd.testing.assert_frame_equal(result.frame, alone.frame)


def test_missing_required_input_is_no_input_not_a_call() -> None:
    _, reader = store()
    result = compute_one(reader, COUNTING, END)
    assert result.frame is None and result.no_input == f"no bars/1d for {END}"
    assert list(compute_sessions(reader, COUNTING, [])) == []


def test_point_in_time_guard() -> None:
    from algotrade.features.framework import runner  # noqa: PLC0415

    future = pd.DataFrame({"session_date": [END, date(2026, 10, 5)]})
    with pytest.raises(AssertionError, match="reached"):
        runner._check_point_in_time(COUNTING, "bars/1d", future, END)


def test_params_and_selection() -> None:
    rollups = list(ROLLUPS.values())
    defaults = rollup_params(None, rollups)
    assert defaults["earnings@v1"] is None
    configs = MemoryConfigStore(
        {("site", "settings", "rollups"): {"price_stats@v1": {"year_sessions": 260}}}
    )
    assert rollup_params(configs, rollups)["price_stats@v1"].year_sessions == 260
    assert [r.key for r in by_key(ROLLUPS, ["earnings@v1"])] == ["earnings@v1"]
    assert len(by_key(ROLLUPS, [])) == len(ROLLUPS)
    with pytest.raises(KeyError, match="unknown rollups"):
        by_key(ROLLUPS, ["nope@v1"])
