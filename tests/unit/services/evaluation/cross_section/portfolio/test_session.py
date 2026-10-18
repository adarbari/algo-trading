"""One session of a portfolio_return outcome (ADR 0074): the value against a blended benchmark
from the constituents' own rows, cash at the bill yield, the session left out (with its reason)
when anything it needs is missing, and the decile figures that are N/A under about 20 names."""

from datetime import date

import pandas as pd
import pytest

from algotrade.services.evaluation.cross_section.portfolio.session import (
    NO_BENCHMARK_ROW,
    NO_CASH_YIELD,
    NO_PICK_RETURN,
    cash_return,
    portfolio_stat,
    ranking_deciles,
    session_value,
    window_returns,
)

DAY = date(2026, 3, 31)
BLEND = (("SPY", 0.6), ("AGG", 0.4))
IDS = {"SPY": "EQ:SPY", "AGG": "EQ:AGG"}


def rows(**returns: float | None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": list(returns),
            "fwd_return": [returns[i] for i in returns],
            "fwd_excess_return": [0.0 if r is None else r - 0.01 for r in returns.values()],
            "outcome_status": ["COMPLETE"] * len(returns),
        }
    )


def test_the_value_is_the_book_minus_the_blend_over_the_same_window() -> None:
    returns = window_returns(rows(**{"EQ:SPY": 0.02, "EQ:AGG": 0.0, "EQ:X": 0.05, "EQ:Y": 0.03}))
    value, why = session_value((("EQ:X", 0.5), ("EQ:Y", 0.5)), BLEND, IDS, returns, None)
    assert why == ""
    assert value == pytest.approx(0.04 - 0.012)  # book 4%, a 60/40 mix of 2% and 0% is 1.2%


def test_a_plain_benchmark_is_its_own_blend() -> None:
    returns = {"EQ:SPY": 0.02, "EQ:X": 0.03}
    value, _ = session_value((("EQ:X", 1.0),), (("SPY", 1.0),), IDS, returns, None)
    assert value == pytest.approx(0.01)


def test_cash_earns_the_bill_yield_scaled_to_the_window() -> None:
    assert cash_return(0.04, 21) == pytest.approx(0.04 * 21 / 252)
    assert cash_return(None, 21) is None and cash_return(float("nan"), 21) is None
    returns = {"EQ:SPY": 0.01, "EQ:AGG": 0.01}
    value, why = session_value((("CASH", 1.0),), BLEND, IDS, returns, cash_return(0.04, 21))
    assert why == "" and value == pytest.approx(0.04 * 21 / 252 - 0.01)  # a cash session is valued


def test_cash_with_no_yield_is_no_value_never_zero() -> None:
    returns = {"EQ:SPY": 0.01, "EQ:AGG": 0.01}
    assert session_value((("CASH", 1.0),), BLEND, IDS, returns, None) == (None, NO_CASH_YIELD)


def test_a_missing_constituent_row_excludes_the_session_with_its_ticker() -> None:
    returns = {"EQ:SPY": 0.01, "EQ:X": 0.02}
    value, why = session_value((("EQ:X", 1.0),), BLEND, IDS, returns, None)
    assert (value, why) == (None, f"{NO_BENCHMARK_ROW}:AGG")


def test_a_constituent_the_reference_does_not_know_excludes_the_session() -> None:
    returns = {"EQ:SPY": 0.01, "EQ:AGG": 0.01, "EQ:X": 0.02}
    ids = {"SPY": "EQ:SPY", "AGG": None}
    assert session_value((("EQ:X", 1.0),), BLEND, ids, returns, None) == (
        None,
        f"{NO_BENCHMARK_ROW}:AGG",
    )


def test_a_held_name_with_no_return_excludes_the_session_never_reweights() -> None:
    returns = {"EQ:SPY": 0.01, "EQ:AGG": 0.01, "EQ:X": 0.02}
    assert session_value((("EQ:X", 0.5), ("EQ:Y", 0.5)), BLEND, IDS, returns, None) == (
        None,
        NO_PICK_RETURN,
    )


def test_a_window_over_a_flagged_bar_or_without_a_return_is_not_a_return() -> None:
    frame = rows(**{"EQ:A": 0.01, "EQ:B": None, "EQ:C": 0.03, "EQ:D": float("nan")})
    frame.loc[frame["instrument_id"] == "EQ:C", "outcome_status"] = "UNMEASURED"
    assert window_returns(frame) == {"EQ:A": 0.01}  # a delisted name's window still counts


def test_a_session_value_is_one_net_value_and_a_hit_when_positive() -> None:
    stat = portfolio_stat(DAY, "BULL", 0.01, "", (("EQ:X", 1.0),), cost_bps=20)
    assert stat.pick_values == pytest.approx((0.008,))  # net of one round trip of 20 bp
    assert (stat.pick_hits, stat.weights, stat.excluded_coverage) == (1, (("EQ:X", 1.0),), 0)
    assert portfolio_stat(DAY, "BULL", 0.001, "", (("EQ:X", 1.0),), cost_bps=20).pick_hits == 0
    assert portfolio_stat(DAY, "BULL", 0.0, "", (("EQ:X", 1.0),), cost_bps=None).pick_hits == 0


def test_a_session_with_no_value_is_left_out_and_says_why() -> None:
    stat = portfolio_stat(DAY, "BULL", None, f"{NO_BENCHMARK_ROW}:AGG", (), cost_bps=20)
    assert (stat.excluded_coverage, stat.pick_values, stat.weights) == (1, (), ())
    assert stat.portfolio_reason == "no_benchmark_row:AGG"


def _universe(n: int) -> tuple[pd.DataFrame, dict[str, float]]:
    ids = [f"EQ:{i:02d}" for i in range(n)]
    frame = pd.DataFrame(
        {
            "instrument_id": ids,
            "fwd_return": 0.0,
            "fwd_excess_return": [0.01 * (n - i) for i in range(n)],  # the best-ranked do best
            "outcome_status": "COMPLETE",
        }
    )
    return frame, {i: float(n - k) for k, i in enumerate(ids)}


def test_deciles_are_not_applicable_under_twenty_ranked_names() -> None:
    frame, scores = _universe(19)
    assert ranking_deciles(frame, scores, 0.0) == ()
    stat = portfolio_stat(DAY, "BULL", 0.01, "", (("EQ:X", 1.0),), None, (), 19)
    assert (stat.spread, stat.top_decile, stat.deciles, stat.ranked) == (None, None, (), 0)


def test_deciles_are_the_rankings_with_twenty_names() -> None:
    frame, scores = _universe(20)
    deciles = ranking_deciles(frame, scores, 0.0)
    assert len(deciles) == 10 and deciles[0] > deciles[-1]
    stat = portfolio_stat(DAY, "BULL", 0.01, "", (("EQ:X", 1.0),), None, deciles, 20)
    assert stat.spread == pytest.approx(deciles[0] - deciles[-1]) and stat.ranked == 20


def test_names_without_a_score_or_a_return_are_not_ranked() -> None:
    frame, scores = _universe(24)
    for gone in list(scores)[:5]:  # five unscored names leave nineteen ranked
        scores.pop(gone)
    assert ranking_deciles(frame, scores, 0.0) == ()
