"""``chain_flow@v1`` on hand-built chains: volume by right (0-DTE included), open interest
(``dte >= 1``), the next expiry, the unusual-activity columns, null volume / OI as 0, each
status with its nulls, point in time through the runner, and the params."""

from dataclasses import replace
from datetime import timedelta

import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.positioning import chain_flow as cf
from tests.helpers.rollup_store import END, quote_row, store, write_chains

GROUP = cf.GROUP
P = cf.ChainFlowParams()
E0, E1, E2 = END, END + timedelta(days=7), END + timedelta(days=30)
LATER = END + timedelta(days=3)
COUNTS = (
    "call_volume", "put_volume", "call_oi", "put_oi", "next_exp_call_volume",
    "next_exp_put_volume", "unusual_contracts",
)  # fmt: skip


def q(uid: str, expiry, right: str, strike: float, volume, oi, bid: float = 1.0, ask: float = 1.2):
    return quote_row(uid, END, expiry, right, strike, bid, ask, volume, oi)


def run(rows: list[dict[str, object]], quoted: tuple[str, ...] = (), params=P) -> pd.DataFrame:
    underlyings = pd.DataFrame({"instrument_id": list(quoted), "price": 100.0, "close": 100.0})
    inputs = {cf.OPTIONS: pd.DataFrame(rows), cf.UNDERLYINGS: underlyings}
    return cf.compute(inputs, END, params).set_index("instrument_id")


CHAIN_A = [
    q("EQ:A", E0, "C", 100, 300, 50),  # expires today: volume counts, OI and unusual do not
    q("EQ:A", E0, "P", 100, 200, 40),
    q("EQ:A", E1, "C", 100, 600, 100, bid=1.0, ask=1.2),  # unusual: 600 > 100, ratio 6, mid 1.1
    q("EQ:A", E1, "C", 105, 50, 10),
    q("EQ:A", E1, "P", 95, 700, 700),  # volume == OI: not unusual, but a ratio of 1
    q("EQ:A", E1, "P", 100, 40, 80),
    q("EQ:A", E2, "C", 100, 1000, 200, bid=0.0, ask=2.0),  # unusual, one-sided: no premium
    q("EQ:A", E2, "P", 100, 10, 300),
]


def test_totals_next_expiry_and_unusual_activity_by_hand() -> None:
    out = run(CHAIN_A).loc["EQ:A"]
    assert out["flow_status"] == "OK"
    assert out["call_volume"] == 300 + 600 + 50 + 1000  # every expiry, 0-DTE included
    assert out["put_volume"] == 200 + 700 + 40 + 10
    assert out["call_oi"] == 100 + 10 + 200  # dte >= 1 only
    assert out["put_oi"] == 700 + 80 + 300
    assert out["next_exp_call_volume"] == 600 + 50  # E1, the first expiry with dte >= 1
    assert out["next_exp_put_volume"] == 700 + 40
    assert out["unusual_contracts"] == 2  # E1 C100 and E2 C100; the 0-DTE contracts never
    assert out["max_vol_oi_ratio"] == pytest.approx(6.0)  # 600 / 100 beats 1000 / 200 and 1
    assert out["unusual_premium_usd"] == pytest.approx(600 * 1.1 * 100)  # one-sided one: none


def test_unusual_edges_zero_oi_and_small_prints() -> None:
    rows = [
        q("EQ:D", E1, "C", 100, 800, 0, bid=2.0, ask=2.2),  # unusual (800 > 0), no ratio (OI 0)
        q("EQ:D", E1, "P", 100, 499, 1),  # below min_unusual_volume: never unusual
        q("EQ:D", E1, "P", 90, 500, 500),  # exactly min volume, volume == OI: ratio, not unusual
    ]
    out = run(rows).loc["EQ:D"]
    assert out["unusual_contracts"] == 1
    assert out["max_vol_oi_ratio"] == pytest.approx(1.0)  # only the 500 / 500 contract
    assert out["unusual_premium_usd"] == pytest.approx(800 * 2.1 * 100)
    strict = run(rows, params=replace(P, min_unusual_volume=801)).loc["EQ:D"]
    assert strict["unusual_contracts"] == 0 and pd.isna(strict["max_vol_oi_ratio"])
    assert pd.isna(strict["unusual_premium_usd"])  # none: null, never 0


def test_every_status_and_its_nulls() -> None:
    rows = [
        *CHAIN_A,
        q("EQ:ZERO", E0, "C", 100, 5, 9),  # only a 0-DTE contract
        q("EQ:NULLS", E1, "C", 100, None, None),  # null volume and OI count as 0
    ]
    out = run(rows, quoted=("EQ:A", "EQ:QUOTED"))
    assert out["flow_status"].to_dict() == {
        "EQ:A": "OK", "EQ:ZERO": "OK", "EQ:NULLS": "OK", "EQ:QUOTED": "NO_CHAIN",
    }  # fmt: skip
    quoted = out.loc["EQ:QUOTED"]
    assert quoted.drop("flow_status").isna().all()  # UNKNOWN, never zero
    zero = out.loc["EQ:ZERO"]
    assert [zero[c] for c in COUNTS[:4]] == [5, 0, 0, 0]
    assert pd.isna(zero["next_exp_call_volume"]) and pd.isna(zero["next_exp_put_volume"])
    assert zero["unusual_contracts"] == 0
    assert zero[["max_vol_oi_ratio", "unusual_premium_usd"]].isna().all()
    nulls = out.loc["EQ:NULLS"]
    assert [nulls[c] for c in COUNTS] == [0, 0, 0, 0, 0, 0, 0]  # a chain, no activity: 0


def test_without_underlying_quotes_and_row_order() -> None:
    inputs = {cf.OPTIONS: pd.DataFrame(CHAIN_A[::-1]), cf.UNDERLYINGS: None}
    out = cf.compute(inputs, END, P).set_index("instrument_id")
    assert out.loc["EQ:A", "call_volume"] == 1950
    assert out.loc["EQ:A", COUNTS].equals(run(CHAIN_A).loc["EQ:A", COUNTS])


def test_point_in_time_through_the_runner() -> None:
    writer, reader = store()
    write_chains(writer, END, CHAIN_A, {"EQ:A": 100.0})
    busier = [{**r, "volume": 9999.0, "ts": r["ts"] + timedelta(days=3)} for r in CHAIN_A]
    write_chains(writer, LATER, busier, {"EQ:A": 100.0})
    frame = compute_one(reader, GROUP, END).frame
    assert frame is not None
    out = frame.set_index("instrument_id").loc["EQ:A"]
    assert out["call_volume"] == 1950 and out["put_volume"] == 950  # the session's partition
    assert str(frame["max_vol_oi_ratio"].dtype) == "float32"
    assert str(frame["call_oi"].dtype) == "int64[pyarrow]"
    assert GROUPS["chain_flow@v1"].table == "rollups/instrument/chain_flow@v1"


def test_params_validate() -> None:
    with pytest.raises(ValueError, match="min_unusual_volume"):
        replace(P, min_unusual_volume=0)
