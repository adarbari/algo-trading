"""``oi_walls@v1``: the docs' worked example (OI summed across expiries 1..60 days out, ties to
the strike nearer spot, strikes at spot count on both sides), expiries outside the window
ignored, every status (NO_SPOT, NO_CHAIN, NO_EXPIRY, NO_OI, PARTIAL, OK), missing OI as 0, and
no rows without a chain partition."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.options import oi_walls as ow
from tests.helpers.rollup_store import END, store, write_chains

NEAR, FAR = END + timedelta(days=14), END + timedelta(days=45)


def quote(underlying: str, expiry: date, right: str, strike: float, oi: float | None) -> dict:
    return {
        "instrument_id": f"OPT:{underlying}:{expiry}:{right}{strike}",
        "underlying_id": underlying,
        "ts": pd.Timestamp(END, tz="UTC") + pd.Timedelta(hours=21),
        "expiry": expiry,
        "right": right,
        "strike": strike,
        "bid": 1.0,
        "ask": 1.1,
        "volume": 10.0,
        "open_interest": oi,
        "iv": 30.0,
        "delta": 0.5,
    }


def walls(options: list[dict], spots: dict[str, float]) -> dict[str, dict[str, object]]:
    writer, reader = store()
    write_chains(writer, END, options, spots)
    frame = compute_one(reader, ow.GROUP, END).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def test_worked_example() -> None:
    a = "EQ:A"
    options = [
        quote(a, NEAR, "C", 100.0, 500),
        quote(a, NEAR, "C", 105.0, 500),
        quote(a, FAR, "C", 105.0, 300),  # 800 at 105 across two expiries
        quote(a, FAR, "C", 110.0, 800),  # a tie with 105: the strike nearer spot wins
        quote(a, NEAR, "C", 95.0, 5000),  # below spot: not a call wall
        quote(a, END, "C", 120.0, 9000),  # expires today: left out
        quote(a, END + timedelta(days=61), "C", 125.0, 9000),  # beyond 60 days
        quote(a, NEAR, "P", 95.0, 700),
        quote(a, NEAR, "P", 90.0, 300),
        quote(a, FAR, "P", 105.0, 9000),  # above spot: not a put wall
    ]
    out = walls(options, {a: 100.0})[a]
    assert out["wall_status"] == "OK"
    assert (out["call_wall"], out["call_wall_oi"]) == (105.0, 800)
    assert (out["put_wall"], out["put_wall_oi"]) == (95.0, 700)


def test_a_strike_at_spot_counts_on_both_sides_and_put_ties_go_nearer() -> None:
    a = "EQ:A"
    options = [
        quote(a, NEAR, "C", 100.0, 400),
        quote(a, NEAR, "P", 100.0, 400),
        quote(a, NEAR, "P", 95.0, 400),  # a tie with 100: 100 is nearer spot
    ]
    out = walls(options, {a: 100.0})[a]
    assert out["call_wall"] == 100.0 and out["put_wall"] == 100.0


def test_every_status_and_missing_oi() -> None:
    options = [
        quote("EQ:NOSPOT", NEAR, "C", 100.0, 100),
        quote("EQ:LATE", END + timedelta(days=90), "C", 100.0, 100),
        quote("EQ:ZERO", NEAR, "C", 105.0, 0),
        quote("EQ:ZERO", NEAR, "P", 95.0, None),  # missing OI counts as 0
        quote("EQ:CALLS", NEAR, "C", 105.0, 50),
        quote("EQ:CALLS", NEAR, "P", 110.0, 50),  # puts only above spot
    ]
    spots = {"EQ:NOCHAIN": 50.0, "EQ:LATE": 100.0, "EQ:ZERO": 100.0, "EQ:CALLS": 100.0}
    out = walls(options, spots)
    assert {i: r["wall_status"] for i, r in out.items()} == {
        "EQ:NOSPOT": "NO_SPOT",
        "EQ:NOCHAIN": "NO_CHAIN",
        "EQ:LATE": "NO_EXPIRY",
        "EQ:ZERO": "NO_OI",
        "EQ:CALLS": "PARTIAL",
    }
    assert out["EQ:CALLS"]["call_wall"] == 105.0 and np.isnan(out["EQ:CALLS"]["put_wall"])
    assert pd.isna(out["EQ:CALLS"]["put_wall_oi"])  # unknown, not 0
    for iid in ("EQ:NOSPOT", "EQ:NOCHAIN", "EQ:LATE", "EQ:ZERO"):
        assert np.isnan(out[iid]["call_wall"]) and np.isnan(out[iid]["put_wall"]), iid


def test_no_chain_partition_means_no_rows() -> None:
    _, reader = store()
    result = compute_one(reader, ow.GROUP, END)
    assert result.frame is None and result.no_input


def test_registered_with_its_params() -> None:
    assert GROUPS["oi_walls@v1"].table == "rollups/instrument/oi_walls@v1"
    assert (ow.GROUP.params.dte_min, ow.GROUP.params.dte_max) == (1, 60)
