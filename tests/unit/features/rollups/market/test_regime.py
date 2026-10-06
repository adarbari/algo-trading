"""``regime@v3``: the scores' arithmetic by hand (credit from high yield, else the EBP), the
macro score's two tiers (each on its own covered-weight scale, ``macro_risk`` the higher; the
curve on after a month of inversion in the last year), the covered-weight scale (an unknown
signal neither adds nor dilutes; below the coverage floor a score is UNKNOWN, never CALM), the
stateless 5-session hold (a one-day STRESS blip holds for 5 sessions), and a backfill equal to
the nightly, deterministic run after run."""

from collections.abc import Mapping
from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_in_memory, compute_one
from algotrade.features.rollups.market import cross_asset, indicators, macro, regime, trend
from algotrade.features.rollups.market.regime import (
    Params,
    Signal,
    macro_risk,
    raw_label,
    score,
    tiers,
)
from tests.helpers.rollup_store import END, store, write_rows

P = Params()
INPUTS = (indicators.GROUP, macro.GROUP, trend.GROUP, cross_asset.GROUP)
CALM: dict[str, object] = {
    **{f"{c.key}_on": False for c in indicators.CARDS},
    "curve_inverted_days_252d": 0, "claims_4w_vs_52w_low": 1.05, "sloos_ci_tightening": 0.0,
    "permits_yoy": 0.02,
    "fedfunds_chg_12m": 0.0, "cpi_yoy": 0.025, "bank_credit_yoy": 0.05,
    "spx_drawdown_252d": -0.02, "spx_ret_252d": 0.12, "xly_vs_xlp": 0.01, "iwm_vs_spy": -0.01,
    "hyg_vs_lqd": 0.005, "turbulence_60d": 14.0, "basket_size": 14, "absorption_shift": 0.2,
}  # fmt: skip
SHOCK = {"spx_trend_200d_on": True, "vix_term_on": True, "breadth_200d_on": True}  # 60: STRESS


def test_the_scores_by_hand() -> None:
    assert (score(CALM, P, "macro").raw, score(CALM, P, "market").raw) == (0.0, 0.0)
    late_cycle = {**CALM, "curve_inverted_days_252d": 40, "hy_oas_on": True, "sahm_on": True,
                  "claims_4w_vs_52w_low": 1.15, "cpi_yoy": 0.05}  # fmt: skip
    m = score(late_cycle, P, "macro")
    assert (m.raw, m.coverage, m.missing) == (20 + 20 + 7 + 6 + 5, 1.0, 0)
    assert m.scaled(P.min_coverage) == 58.0  # everything known: the two scales agree
    early, confirming = tiers(late_cycle, P)
    assert early == pytest.approx(100 * 25 / 35)  # curve 20 + inflation 5 of 35
    assert confirming == pytest.approx(100 * 33 / 65)  # credit 20 + Sahm 7 + claims 6 of 65
    assert macro_risk(early, confirming) == early
    stressed = {**CALM, **SHOCK, "spx_drawdown_252d": -0.10, "xly_vs_xlp": -0.01,
                "turbulence_60d": 28.0}  # fmt: skip
    k = score(stressed, P, "market")
    assert k.raw == 20 + 20 + 20 + 10 + 8 + 8  # leadership: both ratios falling
    assert score({**CALM, "bank_credit_yoy": 0.11}, P, "fragility").raw == 50.0
    assert raw_label(CALM, P) == "CALM"
    assert raw_label(late_cycle, P) == "CAUTION"
    assert raw_label(stressed, P) == "STRESS"
    assert raw_label({**late_cycle, **SHOCK}, P) == "CRISIS"


def test_unknown_signals_neither_add_nor_dilute_and_count_as_missing() -> None:
    market = {*cross_asset.GROUP.columns, *trend.GROUP.columns, *SHOCK}
    no_macro = {k: v for k, v in CALM.items() if k in market}
    m = score(no_macro, P, "macro")
    assert (m.raw, m.coverage, m.missing) == (0.0, 0.0, 10)
    assert np.isnan(m.scaled(P.min_coverage))
    assert raw_label(no_macro, P) is None  # never a false CALM
    half = {**no_macro, "curve_inverted_days_252d": 30, "hy_oas_on": False, "nfci_on": False}
    m = score(half, P, "macro")
    assert (m.raw, m.coverage, m.missing) == (20.0, 0.55, 7)
    assert m.scaled(P.min_coverage) == pytest.approx(100 * 20 / 55)  # 36.4 of what is known
    # the early tier: the curve alone known, 20 of 35 (0.57): on, 100; the confirming tier:
    # credit and NFCI known, 35 of 65 (0.54): off, 0. The higher tier is macro high.
    assert tiers(half, P) == (100.0, 0.0)
    assert raw_label(half, P) == "CAUTION"
    assert raw_label({**half, "curve_inverted_days_252d": 0}, P) == "CALM"
    assert score({}, P, "fragility").coverage == 0.0


def test_every_known_fast_signal_on_reads_100_not_the_share_of_all_weight() -> None:
    """Signals whose windows are longer than the stored bars (turbulence, absorption) are
    unknown: they no longer hold the score below the threshold however many others are on."""
    young = {k: v for k, v in {**CALM, **SHOCK}.items() if k not in ("turbulence_60d",
             "absorption_shift")}  # fmt: skip
    young |= {"spx_drawdown_252d": -0.12, "xly_vs_xlp": -0.01, "hyg_vs_lqd": -0.01}
    k = score(young, P, "market")
    assert (k.raw, k.coverage, k.missing) == (85.0, 0.85, 2)  # v1's market_stress: 85
    assert k.scaled(P.min_coverage) == 100.0
    calmer = {**young, "breadth_200d_on": False, "vix_term_on": False}
    assert score(calmer, P, "market").scaled(P.min_coverage) == pytest.approx(100 * 45 / 85)
    assert raw_label(calmer, P) == "STRESS"  # 52.9 >= 50; v1 read 45: CALM


def test_below_the_coverage_floor_a_score_is_unknown_and_its_raw_is_kept() -> None:
    sparse = {"vix_term_on": True, "xly_vs_xlp": -0.01, "iwm_vs_spy": -0.01, "hyg_vs_lqd": -0.01,
              "turbulence_60d": 28.0, "basket_size": 14}  # fmt: skip
    k = score(sparse, P, "market")
    assert (k.raw, k.coverage) == (43.0, 0.43)  # 2025-04-08 on the owner's store
    assert np.isnan(k.scaled(P.min_coverage))
    young = ("spx_trend_200d_on", "breadth_200d_on", "spx_drawdown_252d", "absorption_shift")
    day = {k: v for k, v in {**CALM, **sparse}.items() if k not in young}
    row = regime.compute(frames(dict.fromkeys(sessions_ending(END, 10), day)), END, P).iloc[0]
    assert pd.isna(row["market_stress"]) and row["market_stress_raw"] == 43.0
    assert row["raw_label"] is None and row["label"] is None


def test_credit_is_the_high_yield_verdict_else_the_excess_bond_premium() -> None:
    no_hy = {k: v for k, v in CALM.items() if k != "hy_oas_on"}
    assert score(no_hy, P, "macro").missing == 1  # neither known: the credit signal is unknown
    assert score({**no_hy, "ebp": 0.006}, P, "macro").raw == 20.0  # before 1997: EBP
    assert score({**no_hy, "ebp": 0.004}, P, "macro") == score(CALM, P, "macro")
    assert score({**CALM, "ebp": 0.03}, P, "macro").raw == 0.0  # high yield known: it decides


def test_the_curve_is_on_after_a_month_of_inversion_in_the_last_year() -> None:
    """Inverted on 21 of the last 252 sessions: on now, inverted or not (the un-inversion that
    comes months before a peak keeps the warning); 20 sessions: off."""
    curve = next(s for s in regime.SIGNALS if s.name == "curve")
    assert curve.tier == "early"
    assert curve.verdict({**CALM, "curve_inverted_days_252d": 21}, P) is True
    assert curve.verdict({**CALM, "curve_inverted_days_252d": 20}, P) is False
    assert curve.verdict({k: v for k, v in CALM.items() if k != "curve_inverted_days_252d"},
                         P) is None  # fmt: skip
    assert curve.verdict({**CALM, "curve_inverted_days_252d": 40},
                         Params(curve_inverted_days=63)) is False  # fmt: skip


def test_either_tier_alone_makes_macro_high() -> None:
    curve_only = {**CALM, "curve_inverted_days_252d": 30}  # 20 of the early tier's 35: 57
    assert tiers(curve_only, P) == (pytest.approx(100 * 20 / 35), 0.0)
    assert raw_label(curve_only, P) == "CAUTION"
    # Fed hikes, permits and inflation without the curve: 15 of 35, 43: not high
    hikes = {**CALM, "fedfunds_chg_12m": 0.03, "permits_yoy": -0.25, "cpi_yoy": 0.06}
    assert tiers(hikes, P)[0] == pytest.approx(100 * 15 / 35)
    assert raw_label(hikes, P) == "CALM"
    # the confirming tier alone: credit and NFCI, 35 of 65 (53.8); credit alone 20 (30.8)
    downturn = {**CALM, "hy_oas_on": True, "nfci_on": True}
    assert tiers(downturn, P) == (0.0, pytest.approx(100 * 35 / 65))
    assert raw_label(downturn, P) == "CAUTION"
    assert raw_label({**downturn, "nfci_on": False}, P) == "CALM"


def test_a_tier_below_its_coverage_floor_is_left_out() -> None:
    """Before 1982 the curve is unknown: the early tier (fed, permits, CPI: 15 of 35) is
    unknown and the confirming tier decides; with neither known macro risk is unknown."""
    no_curve = {k: v for k, v in CALM.items() if k != "curve_inverted_days_252d"}
    early, confirming = tiers(no_curve, P)
    assert np.isnan(early) and confirming == 0.0
    assert macro_risk(early, confirming) == 0.0
    assert np.isnan(macro_risk(np.nan, np.nan))
    assert raw_label({**no_curve, "hy_oas_on": True, "nfci_on": True, "sahm_on": True}, P) == (
        "CAUTION"
    )


def test_weights_must_sum_to_100() -> None:
    with pytest.raises(ValueError, match="macro weights must sum to 100"):
        Params(w_curve=25.0)
    with pytest.raises(ValueError, match="min_coverage"):
        Params(min_coverage=1.5)
    with pytest.raises(ValueError, match="curve_inverted_days"):
        Params(curve_inverted_days=0)


def test_a_macro_signal_has_a_tier_and_no_other_signal_has() -> None:
    def never(v: object, p: object) -> None:
        return None

    with pytest.raises(ValueError, match="tier"):
        Signal("x", "macro", "w_curve", (), never)
    with pytest.raises(ValueError, match="tier"):
        Signal("x", "market", "w_trend", (), never, "early")
    macro_tiers = {s.tier for s in regime.SIGNALS if s.score == "macro"}
    assert macro_tiers == {"early", "confirming"}


def frames(by_day: Mapping[date, Mapping[str, object] | None]) -> dict[str, pd.DataFrame | None]:
    out: dict[str, pd.DataFrame | None] = {}
    for g in INPUTS:
        rows = [
            {"instrument_id": "MKT:US", "session_date": d}
            | {c: v for c, v in values.items() if c in g.columns}
            for d, values in sorted(by_day.items())
            if values is not None
        ]
        out[g.table] = pd.DataFrame(rows) if rows else None
    return out


def labels(by_day: Mapping[date, Mapping[str, object] | None], days: list[date]) -> list[object]:
    return [regime.compute(frames(by_day), d, P).iloc[0]["label"] for d in days]


def test_a_one_day_stress_blip_holds_the_label_for_5_sessions() -> None:
    days = sessions_ending(END, 20)
    by_day: dict[date, Mapping[str, object] | None] = dict.fromkeys(days, CALM)
    by_day[days[8]] = {**CALM, **SHOCK}
    got = labels(by_day, days[8:])
    assert got == ["STRESS"] * 5 + ["CALM"] * 7
    changed = [regime.compute(frames(by_day), d, P).iloc[0]["label_changed"] for d in days[8:]]
    assert changed == [True] * 5 + [True] * 5 + [False] * 2  # vs 5 sessions earlier


def test_an_unknown_session_is_unknown_and_never_holds_an_older_label() -> None:
    days = sessions_ending(END, 12)
    by_day: dict[date, Mapping[str, object] | None] = dict.fromkeys(days, CALM)
    by_day[days[-2]] = {**CALM, **SHOCK}
    by_day[END] = None  # nothing stored for the session
    row = regime.compute(frames(by_day), END, P).iloc[0]
    assert row["label"] is None and row["raw_label"] is None and row["label_changed"] is None
    assert (row["macro_risk_raw"], row["macro_coverage"], row["macro_missing"]) == (0.0, 0.0, 10)
    assert pd.isna(row["macro_risk"]) and pd.isna(row["market_stress"])
    assert pd.isna(row["macro_early"]) and pd.isna(row["macro_confirming"])
    assert pd.isna(row["fragility"])


def write_inputs(by_day: Mapping[date, Mapping[str, object]]) -> object:
    writer, reader = store()
    for g in (macro.GROUP, trend.GROUP, cross_asset.GROUP):
        for d, values in by_day.items():
            write_rows(writer, g.table, d, [{"instrument_id": "MKT:US"} | {
                c: values.get(c) for c in g.columns}])  # fmt: skip
    return writer, reader


def market_inputs(stress_on: date, inverted_days: int = 0) -> dict[date, dict[str, object]]:
    calm = {"curve_10y3m": 0.01, "hy_oas": 0.03, "nfci": -0.3,
            "hy_oas_vs_126d_low": 0.0, "unrate_vs_12m_avg": -0.001, "sahm_gap": 0.0,
            "vix_term_ratio": 0.9, "spx_close_vs_sma200": 0.04, **CALM,
            "curve_inverted_days_252d": inverted_days}  # fmt: skip
    shock = {
        **calm,
        "spx_close_vs_sma200": -0.02,
        "vix_term_ratio": 1.2,
        "spx_drawdown_252d": -0.12,
    }
    return {d: (shock if d == stress_on else calm) for d in sessions_ending(END, 15)}


@pytest.mark.parametrize(
    ("inverted_days", "expected"),
    [(0, ["STRESS"] * 5 + ["CALM"]), (30, ["CRISIS"] * 5 + ["CAUTION"])],
)
def test_backfill_equals_nightly_and_runs_are_deterministic(
    inverted_days: int, expected: list[str]
) -> None:
    days = sessions_ending(END, 15)
    writer, reader = write_inputs(market_inputs(days[9], inverted_days))  # type: ignore[misc]
    groups = [indicators.GROUP, regime.GROUP]
    backfill = compute_in_memory(reader, groups, days)
    again = compute_in_memory(reader, groups, days)
    for one, two in zip(backfill[regime.GROUP.key], again[regime.GROUP.key], strict=True):
        pd.testing.assert_frame_equal(one.frame, two.frame)
    for result in backfill[indicators.GROUP.key]:  # the nightly reads indicators from the store
        write_rows(writer, indicators.GROUP.table, result.session, result.frame.to_dict("records"))  # type: ignore[union-attr]
    for result in backfill[regime.GROUP.key][-6:]:
        nightly = compute_one(reader, regime.GROUP, result.session).frame
        pd.testing.assert_frame_equal(result.frame, nightly)
    got = [r.frame.iloc[0]["label"] for r in backfill[regime.GROUP.key][9:]]  # type: ignore[union-attr]
    # no breadth group stored: breadth unknown, trend + VIX term + drawdown = 50 of the 80 known;
    # the curve inverted on 30 of the last 252 sessions: the early tier high (20 of 35)
    assert got == expected
    stress = backfill[regime.GROUP.key][9].frame.iloc[0]  # type: ignore[union-attr]
    assert (stress["market_stress"], stress["market_stress_raw"]) == (62.5, 50.0)
    early = 100 * 20 / 35 if inverted_days else 0.0
    assert stress["macro_early"] == pytest.approx(early) and stress["macro_confirming"] == 0.0
    assert stress["macro_risk"] == pytest.approx(early)


def test_every_regime_column_is_open() -> None:
    """Scores and labels are our own aggregate, never a third-party value (ADR 0047 on 0028)."""
    assert {f.licence for f in regime.GROUP.features} == {"open"}
