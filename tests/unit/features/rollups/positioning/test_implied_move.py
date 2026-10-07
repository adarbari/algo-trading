"""``implied_move@v1`` on hand-built straddles: the OP4 worked example (S0 101, strikes 100
and 105, straddle 6.22, implied move 0.0616), the spot rule (close, else price), the expiry
choice (the first covering the next report, else the term expiry), one usable strike, every
status, point in time through the runner, and the params."""

from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.features.framework.runner import compute_one
from algotrade.features.registry import GROUPS
from algotrade.features.rollups.positioning import implied_move as im
from tests.helpers.rollup_store import END, quote_row, store, write_chains, write_rows

GROUP = im.GROUP
P = im.ImpliedMoveParams()
E = END + timedelta(days=30)


def legs(uid, expiry, strike, call, put, half=0.05, session=END):
    """The call and put at ``strike``, quoted ``call`` / ``put`` +- ``half``."""
    return [
        quote_row(uid, session, expiry, "C", strike, call - half, call + half),
        quote_row(uid, session, expiry, "P", strike, put - half, put + half),
    ]


def run(rows, spots, earnings=None, params=P):
    """``spots``: {id: (close, price)}; ``earnings``: {id: (report date, "pre" / "post" / ...)}."""
    underlyings = pd.DataFrame(
        {
            "instrument_id": list(spots),
            "close": [c for c, _ in spots.values()],
            "price": [p for _, p in spots.values()],
        }
    )
    reports = None
    if earnings:
        reports = pd.DataFrame(
            {
                "instrument_id": list(earnings),
                "session_date": END,
                "next_earnings_date": [d for d, _ in earnings.values()],
                "earnings_time": [t for _, t in earnings.values()],
            }
        )
    inputs = {im.OPTIONS: pd.DataFrame(rows), im.UNDERLYINGS: underlyings, im.EARNINGS: reports}
    return im.compute(inputs, END, params).set_index("instrument_id")


def worked(uid="EQ:A", expiry=E):
    return [*legs(uid, expiry, 100, 3.60, 2.50), *legs(uid, expiry, 105, 1.40, 5.30)]


def test_the_worked_example_interpolates_the_straddle_to_the_spot() -> None:
    out = run(worked(), {"EQ:A": (101.0, 99.0)}).loc["EQ:A"]  # close 101; price 99 is ignored
    assert out["move_status"] == "OK"
    assert out["straddle_mid"] == pytest.approx(6.22, rel=1e-6)  # 6.10 + 0.60 x 1/5
    assert out["implied_move"] == pytest.approx(6.22 / 101, rel=1e-6)
    assert round(out["implied_move"], 4) == 0.0616
    assert (out["move_expiry"], out["move_dte"], out["move_basis"]) == (E, 30, "TERM")


def test_spot_is_the_close_then_the_price_and_an_exact_strike_is_its_straddle() -> None:
    spots = {"EQ:A": (np.nan, 101.0), "EQ:B": (100.0, 130.0), "EQ:C": (0.0, 101.0)}
    rows = [*worked("EQ:A"), *worked("EQ:B"), *worked("EQ:C")]
    out = run(rows, spots)
    assert out.loc["EQ:A", "straddle_mid"] == pytest.approx(6.22, rel=1e-6)  # price fallback
    assert out.loc["EQ:C", "straddle_mid"] == pytest.approx(6.22, rel=1e-6)  # zero close: price
    assert out.loc["EQ:B", "straddle_mid"] == pytest.approx(6.10, rel=1e-6)  # S0 on a strike
    assert out.loc["EQ:B", "implied_move"] == pytest.approx(0.061, rel=1e-6)


def test_one_usable_strike_is_its_straddle() -> None:
    rows = [
        *legs("EQ:LO", E, 100, 3.60, 2.50),
        quote_row("EQ:LO", END, E, "C", 105, 0.0, 1.5),  # one-sided call: 105 unusable
        quote_row("EQ:LO", END, E, "P", 105, 5.25, 5.35),
        *legs("EQ:HI", E, 105, 1.40, 5.30),
        *legs("EQ:HI", E, 100, 3.60, 2.50, half=2.0),  # 100's legs far too wide
    ]
    out = run(rows, {"EQ:LO": (101.0, 101.0), "EQ:HI": (101.0, 101.0)})
    assert out.loc["EQ:LO", "straddle_mid"] == pytest.approx(6.10, rel=1e-6)
    assert out.loc["EQ:HI", "straddle_mid"] == pytest.approx(6.70, rel=1e-6)
    assert set(out["move_status"]) == {"OK"}


def test_every_status_and_its_nulls() -> None:
    rows = [
        *worked("EQ:OK"),
        *legs("EQ:WIDE", E, 100, 3.60, 2.50, half=1.5),  # spread 3 / 3.6 > 0.35
        *legs("EQ:WIDE", E, 105, 1.40, 5.30, half=1.5),
        quote_row("EQ:NOQ", END, E, "C", 100, 0.0, 3.6),  # bid 0: not two-sided
        quote_row("EQ:NOQ", END, E, "P", 100, 2.4, 2.6),
        quote_row("EQ:NOQ", END, E, "C", 105, 1.4, 1.2),  # crossed
        quote_row("EQ:NOQ", END, E, "P", 105, 5.2, 5.4),
        *worked("EQ:OUT"),  # spot below every strike: no pair around it
        *worked("EQ:NOSPOT"),
        *worked("EQ:SOON", END + timedelta(days=3)),  # under 7 days out
        *worked("EQ:FAR", END + timedelta(days=90)),  # beyond max_dte
    ]
    spots = {
        "EQ:OK": (101.0, 101.0), "EQ:WIDE": (101.0, 101.0), "EQ:NOQ": (101.0, 101.0),
        "EQ:OUT": (90.0, 90.0), "EQ:NOSPOT": (0.0, np.nan), "EQ:SOON": (101.0, 101.0),
        "EQ:FAR": (101.0, 101.0), "EQ:BARE": (101.0, 101.0),
    }  # fmt: skip
    out = run(rows, spots)
    assert out["move_status"].to_dict() == {
        "EQ:OK": "OK", "EQ:WIDE": "WIDE_SPREADS", "EQ:NOQ": "NO_QUOTES", "EQ:OUT": "NO_QUOTES",
        "EQ:NOSPOT": "NO_SPOT", "EQ:SOON": "NO_EXPIRY", "EQ:FAR": "NO_EXPIRY",
        "EQ:BARE": "NO_CHAIN",
    }  # fmt: skip
    for iid in ("EQ:WIDE", "EQ:NOQ", "EQ:OUT"):  # an expiry was chosen, the quotes failed
        row = out.loc[iid]
        assert (row["move_expiry"], row["move_dte"], row["move_basis"]) == (E, 30, "TERM")
        assert row[["implied_move", "straddle_mid"]].isna().all()
    for iid in ("EQ:NOSPOT", "EQ:SOON", "EQ:FAR", "EQ:BARE"):
        assert out.loc[iid].drop("move_status").isna().all()  # UNKNOWN, never zero


def day(n: int) -> date:
    return END + timedelta(days=n)


def chain_of(uid: str, days: list[int]) -> list[dict[str, object]]:
    return [r for d in days for r in worked(uid, END + timedelta(days=d))]


def test_the_earnings_expiry_is_the_first_covering_the_report() -> None:
    days = [7, 20, 45, 70]
    spots = dict.fromkeys(
        ("EQ:PRE", "EQ:ON_POST", "EQ:UNKNOWN", "EQ:FAR", "EQ:OVER", "EQ:TODAY_PRE",
         "EQ:TODAY_POST", "EQ:NONE"), (101.0, 101.0),
    )  # fmt: skip
    rows = [r for uid in spots for r in chain_of(uid, days)]
    earnings = {
        "EQ:PRE": (day(10), "pre"),  # the +20 expiry is the first after it
        "EQ:ON_POST": (day(20), "post"),  # an expiry ON the report day does not cover a post
        "EQ:UNKNOWN": (day(20), "unknown"),
        "EQ:FAR": (day(46), "pre"),  # covered only by the +70 expiry: beyond max_dte, so TERM
        "EQ:OVER": (day(61), "pre"),
        "EQ:TODAY_PRE": (END, "pre"),  # already in today's close: not ahead
        "EQ:TODAY_POST": (END, "post"),  # tonight, after the close: the +7 expiry covers it
    }
    out = run(rows, spots, earnings)
    chosen = out[["move_dte", "move_basis"]].to_dict("index")
    assert chosen["EQ:PRE"] == {"move_dte": 20, "move_basis": "EARNINGS"}
    assert chosen["EQ:ON_POST"] == {"move_dte": 45, "move_basis": "EARNINGS"}
    assert chosen["EQ:UNKNOWN"] == {"move_dte": 45, "move_basis": "EARNINGS"}
    assert chosen["EQ:FAR"] == {"move_dte": 20, "move_basis": "TERM"}  # nearest 30 of 7 / 20 / 45
    assert chosen["EQ:OVER"]["move_basis"] == "TERM"
    assert chosen["EQ:TODAY_PRE"]["move_basis"] == "TERM"
    assert chosen["EQ:TODAY_POST"] == {"move_dte": 7, "move_basis": "EARNINGS"}
    assert chosen["EQ:NONE"]["move_basis"] == "TERM"  # no earnings row


def test_on_the_report_day_a_pre_report_is_covered_by_that_expiry() -> None:
    rows = chain_of("EQ:A", [7, 20, 45])
    out = run(rows, {"EQ:A": (101.0, 101.0)}, {"EQ:A": (END + timedelta(days=20), "pre")})
    assert out.loc["EQ:A", "move_dte"] == 20 and out.loc["EQ:A", "move_basis"] == "EARNINGS"


def test_term_expiry_is_nearest_the_target_ties_to_the_earlier() -> None:
    def pick(days: list[int], params: im.ImpliedMoveParams = P) -> int:
        out = run(chain_of("EQ:A", days), {"EQ:A": (101.0, 101.0)}, params=params)
        return int(out.loc["EQ:A", "move_dte"])

    assert pick([7, 25, 36, 45]) == 25  # off 5 beats off 6
    assert pick([25, 35]) == 25  # a tie: the earlier
    assert pick([6, 7]) == 7  # under 7 days is never a term expiry
    assert pick([30, 59, 60, 61]) == 30
    assert pick([14, 61, 60], replace(P, target_dte=45, max_dte=60)) == 60


def test_point_in_time_through_the_runner() -> None:
    writer, reader = store()
    later = END + timedelta(days=3)
    write_chains(writer, END, worked(), {"EQ:A": 101.0})
    moved = [{**r, "bid": r["bid"] * 3, "ask": r["ask"] * 3} for r in worked("EQ:A")]
    write_chains(writer, later, moved, {"EQ:A": 101.0})
    write_rows(
        writer, im.EARNINGS, END,
        [{"instrument_id": "EQ:A", "next_earnings_date": END + timedelta(days=10),
          "earnings_time": "pre"}],
    )  # fmt: skip
    frame = compute_one(reader, GROUP, END).frame
    assert frame is not None
    out = frame.set_index("instrument_id").loc["EQ:A"]
    assert out["straddle_mid"] == pytest.approx(6.22, rel=1e-6)  # END's partition, not later's
    assert out["move_dte"] == 30 and out["move_basis"] == "EARNINGS"  # END's earnings@v1 row
    assert str(frame["implied_move"].dtype) == "float32"
    assert GROUPS["implied_move@v1"].table == "rollups/instrument/implied_move@v1"


def test_params_validate() -> None:
    with pytest.raises(ValueError, match="target_dte"):
        replace(P, target_dte=6)
    with pytest.raises(ValueError, match="target_dte"):
        replace(P, target_dte=61)
    with pytest.raises(ValueError, match="max_spread_pct"):
        replace(P, max_spread_pct=0)
    narrow = run(
        [*legs("EQ:A", E, 100, 3.60, 2.50, half=0.5), *legs("EQ:A", E, 105, 1.40, 5.30, half=0.5)],
        {"EQ:A": (101.0, 101.0)},
        params=replace(P, max_spread_pct=0.1),  # 1.0 / 3.6 = 0.28: too wide at 0.1
    )
    assert narrow.loc["EQ:A", "move_status"] == "WIDE_SPREADS"
