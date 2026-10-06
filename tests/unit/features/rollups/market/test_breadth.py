"""``market_breadth@v1`` on synthetic universes: known shares, a member without bars is never
counted, the coverage floor and a universe snapshot from after the session give nulls with
their status, ETFs are not members, the Zweig thrust and 90% down days by hand, and a
permutation of ids changes nothing."""

from collections.abc import Sequence
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.market import breadth
from tests.helpers.rollup_store import END, store, write_bars, write_rows
from tests.helpers.stored_frames import universe_rows

GROUP = breadth.GROUP
P = breadth.MarketBreadthParams()
F32 = 2e-7
RISING = np.linspace(50, 100, 260)  # above both averages, at its 52-week closing high
FALLING = np.linspace(100, 50, 260)  # below both, 50% under its high (a bear), at its low
BREADTH = ("pct_above_sma200", "pct_above_sma50", "pct_in_bear", "new_highs_minus_lows_pct",
           "zweig_thrust", "pct_90_down_days_20d")  # fmt: skip


def names(n: int, prefix: str = "S") -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


def market_row(reader: StoreReader, p: breadth.MarketBreadthParams = P) -> dict[str, object]:
    frame = compute_one(reader, GROUP, END, p).frame
    assert frame is not None and list(frame["instrument_id"]) == ["MKT:US"]
    return frame.iloc[0].to_dict()


def six_of_ten(extra_members: Sequence[str] = (), etfs: Sequence[str] = ()) -> StoreReader:
    """Ten stocks with bars: S0-S5 rising, S6-S9 falling; ``extra_members`` are in the universe
    without bars, ``etfs`` are ETF members that all rise."""
    writer, reader = store()
    symbols = names(10)
    closes = {f"EQ:{s}": RISING if i < 6 else FALLING for i, s in enumerate(symbols)}
    closes |= {f"EQ:{s}": RISING for s in etfs}
    days = write_bars(writer, closes)
    rows = universe_rows([*symbols, *extra_members])
    rows += universe_rows(list(etfs), asset_class="ETF", security_type="ETF")
    write_rows(writer, "universe", days[0], rows)
    return reader


def test_six_of_ten_above_by_hand() -> None:
    row = market_row(six_of_ten(etfs=["E1", "E2", "E3"]))  # ETFs are not members
    assert (row["breadth_status"], row["universe_members"], row["universe_coverage"]) == (
        "OK",
        10,
        1.0,
    )
    assert row["pct_above_sma200"] == pytest.approx(0.6, rel=F32)
    assert row["pct_above_sma50"] == pytest.approx(0.6, rel=F32)
    assert row["pct_in_bear"] == pytest.approx(0.4, rel=F32)
    assert row["new_highs_minus_lows_pct"] == pytest.approx((6 - 4) / 10, rel=F32)
    assert row["zweig_thrust"] == False  # noqa: E712 (a stored bool, not Python's False)
    assert row["pct_90_down_days_20d"] == 0.0  # decliners never hold 90% of the dollar volume


def test_a_member_without_bars_is_never_counted() -> None:
    row = market_row(six_of_ten(extra_members=["GONE"]))
    assert row["universe_members"] == 11
    assert row["universe_coverage"] == pytest.approx(10 / 11, rel=F32)
    assert row["pct_above_sma200"] == pytest.approx(0.6, rel=F32)  # over the 10 with bars


def test_below_the_coverage_floor_every_breadth_column_is_null() -> None:
    writer, reader = store()
    symbols = names(10)
    closes = {f"EQ:{s}": RISING for s in symbols}
    days = write_bars(writer, closes, skip={f"EQ:{s}": [259] for s in symbols[7:]})
    write_rows(writer, "universe", days[0], universe_rows(symbols))
    row = market_row(reader)  # 3 of 10 members have no bar on the session
    assert (row["breadth_status"], row["universe_members"]) == ("LOW_COVERAGE", 10)
    assert row["universe_coverage"] == pytest.approx(0.7, rel=F32)
    assert all(pd.isna(row[c]) for c in BREADTH)
    lower = market_row(reader, replace(P, min_coverage=0.7))
    assert lower["breadth_status"] == "OK" and lower["pct_above_sma200"] == 1.0


def test_new_listings_keep_coverage_and_count_only_where_their_window_is_complete() -> None:
    writer, reader = store()
    symbols = names(10)
    young = {f"EQ:{s}": FALLING[-100:] for s in symbols[7:]}  # listed 100 sessions ago
    days = write_bars(writer, {**{f"EQ:{s}": RISING for s in symbols[:7]}, **young})
    write_rows(writer, "universe", days[0], universe_rows(symbols))
    row = market_row(reader)
    assert (row["breadth_status"], row["universe_coverage"]) == ("OK", 1.0)
    assert row["pct_above_sma200"] == 1.0  # over the 7 with 200 sessions of bars
    assert row["pct_above_sma50"] == pytest.approx(0.7, rel=F32)  # over all 10


def test_before_the_first_universe_snapshot_everything_is_null() -> None:
    writer, reader = store()
    days = write_bars(writer, {f"EQ:{s}": RISING for s in names(10)})
    write_rows(writer, "universe", days[-1], universe_rows(names(10)))  # taken on END only
    before = compute_one(reader, GROUP, days[-2]).frame
    assert before is not None
    row = before.iloc[0].to_dict()
    assert row["breadth_status"] == "NO_UNIVERSE"
    assert all(pd.isna(row[c]) for c in ("universe_members", "universe_coverage", *BREADTH))
    assert market_row(reader)["breadth_status"] == "OK"  # the session that sees it


def thrust_closes(n_sessions: int = 260) -> dict[str, np.ndarray]:
    """Ten names flat at 100, then 20 moving sessions: 12 with S0 up 1% and the rest down 1%
    (advancing share 0.1), then 8 with every name up 1% (share 1.0)."""
    flat = n_sessions - 20
    out = {}
    for i, s in enumerate(names(10)):
        steps = [1.01 if i == 0 else 0.99] * 12 + [1.01] * 8
        out[f"EQ:{s}"] = np.r_[np.full(flat, 100.0), 100.0 * np.cumprod(steps)]
    return out


def test_zweig_thrust_and_90_percent_down_days_by_hand() -> None:
    writer, reader = store()
    closes = thrust_closes()
    days = write_bars(writer, closes, volume={k: np.full(260, 1000.0) for k in closes})
    write_rows(writer, "universe", days[0], universe_rows(names(10)))
    row = market_row(reader)
    # the 10-session mean of the advancing share goes from 0.1 to (2 x 0.1 + 8 x 1.0) / 10
    assert row["zweig_thrust"] == True  # noqa: E712
    # 12 of the last 20 sessions: 9 of 10 names down on (about) equal dollar volume is short
    # of 90%, so give the decliners more volume
    assert row["pct_90_down_days_20d"] == 0.0
    writer, reader = store()
    volume = {k: np.full(260, 1000.0 if k == "EQ:S0" else 5000.0) for k in closes}
    days = write_bars(writer, closes, volume=volume)
    write_rows(writer, "universe", days[0], universe_rows(names(10)))
    assert market_row(reader)["pct_90_down_days_20d"] == pytest.approx(12 / 20, rel=F32)


def test_no_advancers_or_decliners_leaves_the_thrust_unknown() -> None:
    writer, reader = store()
    days = write_bars(writer, {f"EQ:{s}": np.full(260, 100.0) for s in names(10)})
    write_rows(writer, "universe", days[0], universe_rows(names(10)))
    row = market_row(reader)
    assert row["breadth_status"] == "OK"
    assert pd.isna(row["zweig_thrust"]) and pd.isna(row["pct_90_down_days_20d"])


def test_a_permutation_of_ids_changes_nothing() -> None:
    rows = []
    for order in (names(10), list(reversed(names(10, prefix="Z")))):
        writer, reader = store()
        closes = {f"EQ:{s}": RISING if i < 6 else FALLING for i, s in enumerate(order)}
        days = write_bars(writer, closes)
        write_rows(writer, "universe", days[0], universe_rows(order))
        rows.append(market_row(reader))
    assert rows[0] == rows[1]


def test_backfill_equals_nightly() -> None:
    writer, reader = store()
    days = write_bars(writer, thrust_closes(265))
    write_rows(writer, "universe", days[0], universe_rows(names(10)))
    for result in compute_sessions(reader, GROUP, days[-6:]):
        nightly = compute_one(reader, GROUP, result.session).frame
        assert result.frame is not None and nightly is not None
        pd.testing.assert_frame_equal(result.frame, nightly)
