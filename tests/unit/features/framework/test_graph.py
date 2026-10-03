"""Groups reading groups: dependency order, cycle and unknown-dependency errors, and an
in-memory chain of groups (the inputs themselves: tests/unit/data/test_feature_inputs.py)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs
from algotrade.features.framework.graph import dependencies, dependency_order, dependents
from algotrade.features.framework.runner import compute_in_memory, compute_one
from tests.helpers.rollup_store import features, series, store, write_bars


def passthrough(frames: Inputs, session: date, params: None) -> pd.DataFrame:
    return pd.DataFrame({"instrument_id": ["EQ:A"], "v": [1.0]})


def make(name: str, *reads: str, lookback: int = 0) -> FeatureGroup:
    tables = [Input(f"rollups/instrument/{r}@v1", lookback=lookback) for r in reads]
    return FeatureGroup(
        name, 1, "", tuple(tables) or (Input("bars/1d"),), features({"v": "float"}), passthrough
    )


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


def counted(frames: Inputs, session: date, params: None) -> pd.DataFrame:
    up = frames["rollups/instrument/base@v1"]
    assert up is not None
    return pd.DataFrame({"instrument_id": ["EQ:A"], "v": [float(len(up))]})


def test_compute_in_memory_feeds_dependencies_without_writing() -> None:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(4)})
    base = make("base")
    top = FeatureGroup(
        "top",
        1,
        "",
        (Input("rollups/instrument/base@v1", lookback=2),),
        features({"v": "float"}),
        counted,
    )
    out = compute_in_memory(reader, [top, base], days[1:])
    assert [r.frame["v"].iloc[0] for r in out["top@v1"] if r.frame is not None] == [1.0, 2.0, 3.0]
    assert reader.table("rollups/instrument/base@v1", days[-1]) is None
    assert compute_one(reader, top, days[-1]).no_input  # nothing stored: no input
