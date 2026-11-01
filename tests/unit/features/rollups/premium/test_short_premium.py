"""``short_premium@v1``: the 0.20-delta, 30-day short put and call, every status with its
nulls, a side kept when the other fails, the stored columns and point in time through the
runner. Equality with the option grid's (0.20, 30-day) cell is held in
``tests/unit/services/read/options/test_grid.py``."""

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.options.iv30 import DIVIDENDS, OPTIONS, RATES, UNDERLYINGS
from algotrade.features.rollups.premium import short_premium as sp
from tests.helpers.rollup_store import END, chain_rows, quote_row, store, write_chains, write_curve

E30, E50 = (END + timedelta(days=d) for d in (30, 50))
FINE = tuple(float(k) for k in np.arange(70.0, 130.5, 0.5))


def run(
    options: list[dict[str, object]],
    spots: dict[str, float],
    yields: dict[str, float] | None = None,
) -> pd.DataFrame:
    inputs = {
        OPTIONS: pd.DataFrame(options),
        RATES: pd.DataFrame({"tenor_days": [30, 365], "rate_cont": [0.03, 0.03]}),
        UNDERLYINGS: pd.DataFrame(
            {"instrument_id": list(spots), "price": list(spots.values()), "iv30": 30.0}
        ),
        DIVIDENDS: pd.DataFrame(
            {"instrument_id": list(yields or {}), "session_date": [END] * len(yields or {}),
             "div_yield": list((yields or {}).values())}
        ),
    }  # fmt: skip
    return sp.compute(inputs, END, None).set_index("instrument_id")


def test_both_sides_at_020_delta_about_30_days() -> None:
    out = run(chain_rows("EQ:A", END, 100.0, {E30: 0.25}, 0.03, strikes=FINE), {"EQ:A": 100.0})
    row = out.loc["EQ:A"]
    assert row["premium_status"] == "OK" and row["target_expiry"] == E30 and row["target_dte"] == 30
    assert row["put_strike"] < 100 < row["call_strike"]
    assert row["put_breakeven"] < row["put_strike"] and row["call_breakeven"] < 100
    assert row["put_yield_ann"] > 0 and row["call_yield_ann"] > 0


def test_every_failing_step_names_itself() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {E30: 0.25}, 0.03, strikes=FINE)
    far = chain_rows("EQ:FAR", END, 100.0, {E50: 0.25}, 0.03, strikes=FINE)
    sparse = chain_rows("EQ:SPARSE", END, 100.0, {E30: 0.25}, 0.03, strikes=(50.0, 100.0, 150.0))
    one_sided = [quote_row("EQ:ONE", END, E30, r, 100.0, 0.0, 0.5, 1.0, 5.0) for r in ("P", "C")]
    out = run(
        rows + far + sparse + one_sided,
        {"EQ:A": 100.0, "EQ:FAR": 100.0, "EQ:SPARSE": 100.0, "EQ:ONE": 100.0,
         "EQ:NOSPOT": 0.0, "EQ:NOCHAIN": 10.0},
    )  # fmt: skip
    status = out["premium_status"].to_dict()
    assert status == {
        "EQ:A": "OK", "EQ:FAR": "NO_EXPIRY", "EQ:SPARSE": "NO_STRIKE", "EQ:ONE": "ILLIQUID",
        "EQ:NOSPOT": "NO_SPOT", "EQ:NOCHAIN": "NO_CHAIN",
    }  # fmt: skip
    assert out.loc["EQ:FAR", ["put_strike", "call_strike", "target_expiry"]].isna().all()


def test_a_side_found_keeps_its_columns_when_the_other_fails() -> None:
    puts = [
        r
        for r in chain_rows("EQ:A", END, 100.0, {E30: 0.25}, 0.03, strikes=FINE)
        if r["right"] == "P"
    ]
    out = run(puts, {"EQ:A": 100.0}).loc["EQ:A"]
    assert out["premium_status"] == "ILLIQUID"  # the calls have no quote
    assert out["put_strike"] > 0 and pd.isna(out["call_strike"])


def test_point_in_time_through_the_runner() -> None:
    writer, reader = store()
    later = END + timedelta(days=3)
    write_curve(writer, END, 0.03)
    write_chains(
        writer,
        END,
        chain_rows("EQ:A", END, 100.0, {E30: 0.25}, 0.03, strikes=FINE),
        {"EQ:A": 100.0},
    )
    write_chains(
        writer,
        later,
        chain_rows("EQ:A", later, 60.0, {E30: 0.9}, 0.03, strikes=FINE),
        {"EQ:A": 60.0},
    )
    frame = compute_one(reader, sp.GROUP, END).frame
    assert frame is not None
    out = frame.set_index("instrument_id").loc["EQ:A"]
    assert out["target_dte"] == 30 and out["put_strike"] == pytest.approx(95.0, abs=3)
    assert str(frame["put_yield_ann"].dtype) == "float32"
    assert GROUPS["short_premium@v1"].table == "rollups/instrument/short_premium@v1"


def test_a_curve_taken_from_after_the_session_gives_no_rows() -> None:
    rows = chain_rows("EQ:A", END, 100.0, {E30: 0.25}, 0.03, strikes=FINE)
    inputs = {
        OPTIONS: pd.DataFrame(rows),
        RATES: pd.DataFrame(
            {"tenor_days": [30, 365], "rate_cont": [0.03, 0.03], "pre_snapshot": [True, True]}
        ),
        UNDERLYINGS: pd.DataFrame({"instrument_id": ["EQ:A"], "price": [100.0], "iv30": 30.0}),
    }
    out = sp.compute(inputs, END, None)
    assert out.empty and list(out.columns) == ["instrument_id", *sp.COLUMNS]
