"""``relative_strength@v1`` on hand-built bars: SPY, two sector ETFs and a few stocks with their
symbol map, universe and company snapshots. The relative strength, its line high and trend, the
percentiles (a strict "below", ties, a non-member, the member floor), the sector columns and
their rank are checked by hand; a missing SPY, sector, gap, universe or company snapshot gives
null, and a session never sees a later snapshot or bar."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.features.framework.runner import compute_one, compute_sessions
from algotrade.features.rollups.relative import relative_strength as rs
from tests.helpers.rollup_store import END, store, write_bars, write_rows
from tests.helpers.stored_frames import universe_rows, write_reference

GROUP = rs.GROUP
P = replace(rs.RelativeStrengthParams(), min_members=3, min_sector_etfs=2)
N = rs.LOOKBACK + 1  # closes a session reads: 253
F32 = 2e-7
DAYS = sessions_ending(END, N)


def at(points: Mapping[int, float], base: float = 100.0) -> np.ndarray:
    """``N`` closes of ``base`` with the close ``ago`` sessions before the last set."""
    out = np.full(N, base)
    for ago, value in points.items():
        out[N - 1 - ago] = value
    return out


# SPY: 63-session return 0.10, 252-session 0.375; 20 sessions ago the 63-session return was 0.05.
CLOSES = {
    "EQ:SPY": at({0: 110, 20: 105, 252: 80}),
    "EQ:A": at({0: 121, 5: 100, 20: 110}),  # 63d 0.21; 20 sessions ago 0.10; 5d 0.21
    "EQ:B": at({0: 105, 5: 105, 10: 130}),  # 63d 0.05; a spike 10 sessions ago; 5d 0
    "EQ:C": at({0: 90}),  # 63d -0.10, 5d -0.10
    "EQ:D": at({0: 100}),  # 63d 0, 5d 0
    "EQ:G": at({0: 100, 5: 99, 252: 50}),  # 63d 0, 5d 100/99 - 1, 252d 1.0
    "EQ:F": at({0: 200}),  # not in the universe: 63d 1.0, 5d 1.0
    "EQ:XLK": at({0: 110}),  # 63d 0.10
    "EQ:XLV": at({0: 95}),  # 63d -0.05
}
MEMBERS = ["A", "B", "C", "D", "G"]
COMPANIES = {
    "A": "Technology",
    "B": "Health Care",
    "C": None,
    "D": "Aerospace",
    "G": "Financials",
    "XLK": "Financials",  # a fund's SIC code maps to a sector: the universe says it is an ETF
}


def company_rows(sectors: Mapping[str, str | None]) -> list[dict[str, object]]:
    return [
        {"instrument_id": f"EQ:{s}", "symbol": s, "cik": "1", "name": f"{s} Inc", "sic": "1",
         "sector": sector, "fetched_on": END}
        for s, sector in sectors.items()
    ]  # fmt: skip


def build(
    closes: Mapping[str, np.ndarray] = CLOSES,
    *,
    upto: int = N - 1,
    members: list[str] | None = MEMBERS,
    sectors: Mapping[str, str | None] | None = COMPANIES,
    skip: Mapping[str, list[int]] | None = None,
    snapshots_on: int = 0,
    later_members: list[str] | None = None,
) -> StoreReader:
    """A store with the bars up to session index ``upto``, the reference (the symbol map of
    ``closes``), the universe (``members`` as stocks; SPY and the ETFs as ETFs) and the company
    snapshot, the last three stored on session ``snapshots_on``."""
    writer, reader = store()
    write_bars(writer, {i: c[: upto + 1] for i, c in closes.items()}, end=DAYS[upto], skip=skip)
    day = DAYS[snapshots_on]
    write_reference(writer, day, {i[3:]: i for i in closes})
    if members is not None:
        etfs = universe_rows(["SPY", "XLK", "XLV"], asset_class="ETF", security_type="ETF")
        write_rows(writer, "universe", day, [*universe_rows(members), *etfs])
    if later_members is not None:
        write_rows(writer, "universe", DAYS[-1], universe_rows(later_members))
    if sectors is not None:
        write_rows(writer, "instruments/company", day, company_rows(sectors))
    return reader


def result(
    reader: StoreReader, p: rs.RelativeStrengthParams = P, session: date = END
) -> dict[str, dict[str, object]]:
    """Every row of the session by instrument id."""
    frame = compute_one(reader, GROUP, session, p).frame
    assert frame is not None
    return frame.set_index("instrument_id").to_dict("index")


def null(value: object) -> bool:
    return bool(pd.isna(value))


def test_relative_strength_against_spy_by_hand() -> None:
    out = result(build())
    a, b = out["EQ:A"], out["EQ:B"]
    assert a["rs_spy_63d"] == pytest.approx(1.21 / 1.10 - 1, rel=F32)  # 0.10
    assert a["rs_spy_252d"] == pytest.approx(1.21 / 1.375 - 1, rel=F32)  # -0.12: SPY ran more
    assert b["rs_spy_63d"] == pytest.approx(1.05 / 1.10 - 1, rel=F32)
    assert out["EQ:SPY"]["rs_spy_63d"] == 0 and out["EQ:SPY"]["rs_spy_252d"] == 0
    # 20 sessions earlier A's 63-session return was 0.10 against SPY's 0.05
    before = 1.10 / 1.05 - 1
    assert a["rs_spy_trend_20d"] == pytest.approx((1.21 / 1.10 - 1) - before, rel=1e-5)
    assert a["rs_spy_trend_20d"] > 0  # improving
    b_before = 1.0 / 1.05 - 1  # B's close 20 sessions ago was 100: flat against SPY's +5%
    assert b["rs_spy_trend_20d"] == pytest.approx((1.05 / 1.10 - 1) - b_before, rel=1e-4)


def test_rs_line_high_needs_today_to_be_the_highest_of_the_252_sessions() -> None:
    out = result(build())
    assert out["EQ:A"]["rs_line_high_252d"] == True  # noqa: E712 (a stored bool)
    assert out["EQ:SPY"]["rs_line_high_252d"] == True  # noqa: E712 (a flat line ties itself)
    # B's line was 1.30 ten sessions ago (130 / 100) and 0.95 today
    assert out["EQ:B"]["rs_line_high_252d"] == False  # noqa: E712
    # C closed below its own start, so its line is below the 1.0 of every earlier session
    assert out["EQ:C"]["rs_line_high_252d"] == False  # noqa: E712


def test_rs_line_window_is_252_sessions_not_253() -> None:
    closes = {**CLOSES, "EQ:A": at({0: 121, 252: 400})}  # a line of 5.0 exactly 252 sessions ago
    assert result(build(closes))["EQ:A"]["rs_line_high_252d"] == True  # noqa: E712


def test_percentiles_count_members_strictly_below_with_ties_and_a_non_member() -> None:
    out = result(build())
    quarter = {s: out[f"EQ:{s}"]["mom_pctile_63d"] for s in "ABCDGF"}
    # member 63-session returns: C -0.10, D 0, G 0, B 0.05, A 0.21
    assert quarter["C"] == 0 and quarter["B"] == pytest.approx(3 / 5, rel=F32)
    assert quarter["A"] == pytest.approx(4 / 5, rel=F32)
    assert quarter["D"] == quarter["G"] == pytest.approx(1 / 5, rel=F32)  # a tie is not below
    assert quarter["F"] == 1.0  # not a member: ranked against the five, above every one
    week = {s: out[f"EQ:{s}"]["ret_5d_pctile"] for s in "ABCDGF"}
    # member 5-session returns: C -0.10, B 0, D 0, G 0.0101, A 0.21
    assert week["C"] == 0 and week["B"] == week["D"] == pytest.approx(1 / 5, rel=F32)
    assert week["G"] == pytest.approx(3 / 5, rel=F32) and week["A"] == pytest.approx(4 / 5)
    year = {s: out[f"EQ:{s}"]["mom_pctile_252d"] for s in "ABCDGF"}
    # member 252-session returns: C -0.10, D 0, B 0.05, A 0.21, G 1.0 (F ties G's 1.0)
    assert year["G"] == pytest.approx(4 / 5, rel=F32) and year["F"] == pytest.approx(4 / 5)
    assert year["A"] == pytest.approx(3 / 5, rel=F32) and year["C"] == 0


def test_percentiles_are_null_below_the_member_floor_or_without_a_universe() -> None:
    few = result(build(), replace(P, min_members=6))  # five members have a return
    assert all(null(r[c]) for r in few.values() for c in rs.PERCENTILES.values())
    assert not null(few["EQ:A"]["rs_spy_63d"])  # nothing else depends on the universe
    none = result(build(members=None))
    assert all(null(r[c]) for r in none.values() for c in rs.PERCENTILES.values())
    etfs_only = result(build(members=[]))
    assert null(etfs_only["EQ:A"]["mom_pctile_63d"])  # ETFs are never members


def test_a_partial_day_gives_no_percentile() -> None:
    reader = build(members=[*MEMBERS, "GONE"])  # 5 of 6 members have a bar: 0.83
    out = result(reader)
    assert all(null(r[c]) for r in out.values() for c in rs.PERCENTILES.values())
    assert not null(out["EQ:A"]["rs_spy_63d"])
    lenient = result(reader, replace(P, min_coverage=0.8))
    assert lenient["EQ:A"]["mom_pctile_63d"] == pytest.approx(
        4 / 5, rel=F32
    )  # GONE has no return: not in the pool


def test_a_member_without_a_known_return_is_not_counted_and_has_no_percentile() -> None:
    reader = build(skip={"EQ:C": [N - 30], "EQ:D": [N - 40]})  # gaps in C's and D's 63 windows
    out = result(reader, replace(P, min_members=3))
    assert null(out["EQ:C"]["mom_pctile_63d"]) and null(out["EQ:D"]["mom_pctile_63d"])
    # the pool is G 0, B 0.05, A 0.21 (C and D left it): A is above two of three
    assert out["EQ:A"]["mom_pctile_63d"] == pytest.approx(2 / 3, rel=F32)
    assert out["EQ:G"]["mom_pctile_63d"] == 0
    floor = result(reader, replace(P, min_members=4))  # only three members have a return
    assert null(floor["EQ:A"]["mom_pctile_63d"])


def test_sector_columns_by_hand() -> None:
    out = result(build())
    a, b = out["EQ:A"], out["EQ:B"]
    assert a["sector_etf"] == "XLK" and b["sector_etf"] == "XLV"
    assert a["sector_ret_63d"] == pytest.approx(0.10, rel=F32)
    assert b["sector_ret_63d"] == pytest.approx(-0.05, rel=F32)
    assert a["rs_sector_63d"] == pytest.approx(1.21 / 1.10 - 1, rel=F32)
    assert b["rs_sector_63d"] == pytest.approx(1.05 / 0.95 - 1, rel=F32)
    assert (a["sector_rank_63d"], b["sector_rank_63d"]) == (1, 2)  # XLK beat XLV


def test_sector_columns_are_null_when_the_sector_or_its_etf_is_unknown() -> None:
    out = result(build())
    assert null(out["EQ:C"]["sector_etf"])  # the snapshot has no sector for C
    assert null(out["EQ:D"]["sector_etf"])  # a sector without an ETF
    assert null(out["EQ:F"]["sector_etf"]) and null(out["EQ:SPY"]["sector_etf"])  # no company row
    assert null(out["EQ:XLK"]["sector_etf"])  # a company row with a sector, but an ETF
    g = out["EQ:G"]  # Financials -> XLF, which is not in the symbol map
    assert g["sector_etf"] == "XLF"
    assert all(null(g[c]) for c in ("sector_ret_63d", "rs_sector_63d", "sector_rank_63d"))
    plain = result(build(sectors=None))  # no company snapshot at all
    assert all(null(r[c]) for r in plain.values() for c in rs.COLUMNS if c.startswith("sector"))
    assert not null(plain["EQ:A"]["rs_spy_63d"])


def test_sector_rank_needs_min_sector_etfs_and_ties_share_the_better_rank() -> None:
    out = result(build(), replace(P, min_sector_etfs=3))  # only two ETFs have a return
    assert null(out["EQ:A"]["sector_rank_63d"]) and not null(out["EQ:A"]["sector_ret_63d"])
    closes = {**CLOSES, "EQ:XLV": at({0: 110})}  # XLV ties XLK at 0.10
    tied = result(build(closes))
    assert tied["EQ:A"]["sector_rank_63d"] == tied["EQ:B"]["sector_rank_63d"] == 1


def test_a_gap_in_a_window_makes_the_value_null_never_a_shorter_window() -> None:
    out = result(build(skip={"EQ:A": [N - 30]}))  # A has no bar 29 sessions ago
    a = out["EQ:A"]
    for column in ("rs_spy_63d", "rs_spy_252d", "rs_line_high_252d", "rs_spy_trend_20d",
                   "rs_sector_63d", "mom_pctile_63d", "mom_pctile_252d"):  # fmt: skip
        assert null(a[column]), column
    assert not null(a["ret_5d_pctile"])  # the 5-session window is whole
    assert a["sector_etf"] == "XLK"
    spy_gap = result(build(skip={"EQ:SPY": [N - 30]}))  # SPY's gap nulls every SPY comparison
    assert null(spy_gap["EQ:A"]["rs_spy_63d"]) and null(spy_gap["EQ:A"]["rs_line_high_252d"])
    assert not null(spy_gap["EQ:A"]["rs_sector_63d"])


def test_a_trend_needs_the_63_session_return_twenty_sessions_ago() -> None:
    out = result(build(skip={"EQ:A": [N - 21 - 63]}))  # a gap in A's earlier 63-session window
    assert null(out["EQ:A"]["rs_spy_trend_20d"]) and not null(out["EQ:A"]["rs_spy_63d"])


def test_without_spy_in_the_symbol_map_only_the_spy_columns_are_null() -> None:
    closes = {i: c for i, c in CLOSES.items() if i != "EQ:SPY"}
    out = result(build(closes))
    a = out["EQ:A"]
    for column in ("rs_spy_63d", "rs_spy_252d", "rs_line_high_252d", "rs_spy_trend_20d"):
        assert null(a[column]), column
    assert a["mom_pctile_63d"] == pytest.approx(4 / 5, rel=F32) and a["sector_etf"] == "XLK"


def test_one_row_per_instrument_with_a_bar_on_the_session() -> None:
    reader = build(skip={"EQ:D": [N - 1]})
    frame = compute_one(reader, GROUP, END, P).frame
    assert frame is not None and "EQ:D" not in set(frame["instrument_id"])
    assert frame["instrument_id"].is_unique
    assert list(frame.columns) == ["instrument_id", *rs.COLUMNS]


def test_a_session_never_sees_a_later_company_or_universe_snapshot() -> None:
    late = build(snapshots_on=N - 1)  # both snapshots are stored on the last session
    earlier = DAYS[-2]
    before = result(late, session=earlier)
    assert all(null(r[c]) for r in before.values() for c in ("sector_etf", "mom_pctile_63d"))
    on_the_day = result(late)  # the day they were stored they are known
    assert on_the_day["EQ:A"]["sector_etf"] == "XLK" and not null(
        on_the_day["EQ:A"]["mom_pctile_63d"]
    )


def test_the_session_sees_the_latest_universe_snapshot_on_or_before_it() -> None:
    out = result(build(later_members=["A", "B", "C", "G"]))  # D left the universe on the session
    assert out["EQ:A"]["mom_pctile_63d"] == pytest.approx(3 / 4, rel=F32)  # four members now
    assert out["EQ:D"]["mom_pctile_63d"] == pytest.approx(1 / 4, rel=F32)  # still ranked, no member


def test_a_backfill_equals_the_per_session_compute() -> None:
    reader = build()
    picks = [DAYS[-40], DAYS[-1]]
    backfilled = {r.session: r.frame for r in compute_sessions(reader, GROUP, picks, P)}
    for day in picks:
        k = DAYS.index(day)
        alone = compute_one(build(upto=k), GROUP, day, P).frame
        pd.testing.assert_frame_equal(alone, backfilled[day])


def test_params_are_validated() -> None:
    bad_params = ({"min_members": 0}, {"min_coverage": 1.5}, {"min_sector_etfs": 0},
                  {"min_sector_etfs": 12})  # fmt: skip
    for bad in bad_params:
        with pytest.raises(ValueError, match="must be"):
            rs.RelativeStrengthParams(**bad)


def test_returns_and_percentile_helpers() -> None:
    close = np.array([[100.0, 100.0], [110.0, np.nan], [121.0, 90.0]])
    assert rs.ret(close, 2).tolist()[0] == pytest.approx(0.21) and np.isnan(rs.ret(close, 2)[1])
    assert np.isnan(rs.ret(close, 3)).all()  # a window longer than the history
    assert rs.ret(close, 1, back=1)[0] == pytest.approx(0.10)
    assert rs.relative(np.array([0.21, np.nan]), 0.10).tolist()[0] == pytest.approx(1.21 / 1.10 - 1)
    assert np.isnan(rs.relative(np.array([0.1]), -1.0)).all()  # a zero denominator
    ranks = rs.percentile(np.array([1.0, 2.0, 2.0, np.nan]), np.array([True, True, True, True]), 1)
    assert ranks[:3].tolist() == [0.0, 1 / 3, 1 / 3] and np.isnan(ranks[3])
