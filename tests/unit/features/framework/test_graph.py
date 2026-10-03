"""Rollups reading rollups: dependency order, cycle and unknown-dependency errors, and the
rollup-table, event-date and rates loaders (store rows, this run's rows winning)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.features.framework import inputs
from algotrade.features.framework.declaration import Input, Inputs, Rollup
from algotrade.features.framework.graph import dependencies, dependency_order, dependents
from algotrade.features.framework.runner import compute_in_memory, compute_one
from tests.rollup_helpers import (
    END,
    series,
    store,
    write_bars,
    write_curve,
    write_dividends,
    write_split,
)
from tests.storage_helpers import stamped


def passthrough(frames: Inputs, session: date, params: None) -> pd.DataFrame:
    return pd.DataFrame({"instrument_id": ["EQ:A"], "v": [1.0]})


def make(name: str, *reads: str, lookback: int = 0) -> Rollup:
    tables = [Input(f"rollups/instrument/{r}@v1", lookback=lookback) for r in reads]
    return Rollup(name, 1, "", tuple(tables) or (Input("bars/1d"),), {"v": "float"}, passthrough)


def test_dependency_order_is_topological_and_stable() -> None:
    a, b, c, d = make("a"), make("b", "c"), make("c", "a"), make("d")
    assert [r.key for r in dependency_order([b, a, c, d])] == ["a@v1", "d@v1", "c@v1", "b@v1"]
    assert dependencies(b) == ("c@v1",)
    assert dependents([a, b, c, d], "a@v1") == {"c@v1", "b@v1"}


def test_cycles_unknown_and_duplicate_rollups_fail() -> None:
    with pytest.raises(ValueError, match=r"cycle: (x@v1 -> y@v1 -> x@v1|y@v1 -> x@v1 -> y@v1)"):
        dependency_order([make("x", "y"), make("y", "x")])
    with pytest.raises(ValueError, match="cycle: self@v1 -> self@v1"):
        dependency_order([make("self", "self")])
    with pytest.raises(ValueError, match=r"unregistered rollups \['nope@v1'\]"):
        dependency_order([make("x", "nope")])
    with pytest.raises(ValueError, match="twice"):
        dependency_order([make("x"), make("x")])


def test_rollup_input_reads_store_and_this_runs_rows_win() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(5)})
    table = "rollups/instrument/up@v1"
    for i, day in enumerate(days[:4]):
        rows = stamped([{"instrument_id": "EQ:A", "v": float(i)}], day, f"r{i}")
        writer.write_table(table, day, f"r{i}", rows)
    mine = pd.DataFrame({"instrument_id": ["EQ:A"], "v": [99.0]})
    loaded = inputs.load_input(reader, table, days[2:], 2, {table: {days[3]: mine, days[4]: None}})
    window = loaded.at(days[3], 2)
    assert window is not None
    assert list(window["v"]) == [1.0, 2.0, 99.0] and list(window["session_date"]) == days[1:4]
    assert "run_id" not in window.columns
    assert loaded.at(days[4], 2) is None  # computed here with no rows: no stale stored rows
    assert inputs.load_input(reader, "rollups/instrument/none@v1", [END], 0).at(END, 0) is None
    assert inputs.has_loader(table) and not inputs.has_loader("bars/7m")


def test_event_inputs_are_by_event_date_and_never_later() -> None:
    writer, reader = store()
    write_dividends(
        writer,
        [
            ("EQ:A", END - timedelta(days=30), 0.5, "recurring"),
            ("EQ:A", END + timedelta(days=10), 0.5, "recurring"),  # declared, not yet ex
        ],
    )
    write_split(writer, "EQ:A", END - timedelta(days=3), 2.0, END)
    divs = inputs.load_input(reader, "events/dividend", [END], 30).at(END, 30)
    assert divs is not None and list(divs["event_date"]) == [END - timedelta(days=30)]
    assert "session_date" not in divs.columns
    splits = inputs.load_input(reader, "events/split", [END], 1).at(END, 1)
    assert splits is not None and splits.empty  # 3 days back is outside 1 session
    _, empty = store()
    assert inputs.load_input(empty, "events/dividend", [END], 5).at(END, 5).empty  # type: ignore[union-attr]


def test_rates_input_is_the_curve_the_session_sees() -> None:
    writer, reader = store()
    loaded = inputs.load_input(reader, "rates/treasury", [END], 0)
    assert loaded.at(END, 0) is None
    write_curve(writer, END - timedelta(days=1), 0.04)
    frame = loaded.at(END, 0)
    assert frame is not None and set(frame["curve_date"]) == {END - timedelta(days=1)}
    assert list(frame["tenor_days"]) == [30, 91, 365] and not frame["pre_snapshot"].any()


def counted(frames: Inputs, session: date, params: None) -> pd.DataFrame:
    up = frames["rollups/instrument/base@v1"]
    assert up is not None
    return pd.DataFrame({"instrument_id": ["EQ:A"], "v": [float(len(up))]})


def test_compute_in_memory_feeds_dependencies_without_writing() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(4)})
    base = make("base")
    top = Rollup(
        "top",
        1,
        "",
        (Input("rollups/instrument/base@v1", lookback=2),),
        {"v": "float"},
        counted,
    )
    out = compute_in_memory(reader, [top, base], days[1:])
    assert [r.frame["v"].iloc[0] for r in out["top@v1"] if r.frame is not None] == [1.0, 2.0, 3.0]
    assert reader.table("rollups/instrument/base@v1", days[-1]) is None
    assert compute_one(reader, top, days[-1]).no_input  # nothing stored: no input
