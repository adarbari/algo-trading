"""``regime@v1``: the scores' arithmetic by hand (credit from high yield, else the EBP), the
coverage rule (no macro data is UNKNOWN, never CALM), the stateless 5-session hold (a one-day
STRESS blip holds for 5 sessions), and a backfill equal to the nightly, deterministic run after
run."""

from collections.abc import Mapping
from datetime import date

import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.runner import compute_in_memory, compute_one
from algotrade.features.rollups.market import cross_asset, indicators, macro, regime, trend
from algotrade.features.rollups.market.regime import Params, raw_label, score
from tests.helpers.rollup_store import END, store, write_rows

P = Params()
INPUTS = (indicators.GROUP, macro.GROUP, trend.GROUP, cross_asset.GROUP)
CALM: dict[str, object] = {
    **{f"{c.key}_on": False for c in indicators.CARDS},
    "claims_4w_vs_52w_low": 1.05, "sloos_ci_tightening": 0.0, "permits_yoy": 0.02,
    "fedfunds_chg_12m": 0.0, "cpi_yoy": 0.025, "bank_credit_yoy": 0.05,
    "spx_drawdown_252d": -0.02, "spx_ret_252d": 0.12, "xly_vs_xlp": 0.01, "iwm_vs_spy": -0.01,
    "hyg_vs_lqd": 0.005, "turbulence_60d": 14.0, "basket_size": 14, "absorption_shift": 0.2,
}  # fmt: skip
SHOCK = {"spx_trend_200d_on": True, "vix_term_on": True, "breadth_200d_on": True}  # 60: STRESS


def test_the_scores_by_hand() -> None:
    assert (score(CALM, P, "macro").value, score(CALM, P, "market").value) == (0.0, 0.0)
    late_cycle = {**CALM, "curve_10y3m_on": True, "hy_oas_on": True, "sahm_on": True,
                  "claims_4w_vs_52w_low": 1.15, "cpi_yoy": 0.05}  # fmt: skip
    m = score(late_cycle, P, "macro")
    assert (m.value, m.coverage, m.missing) == (20 + 20 + 7 + 6 + 5, 1.0, 0)
    stressed = {**CALM, **SHOCK, "spx_drawdown_252d": -0.10, "xly_vs_xlp": -0.01,
                "turbulence_60d": 28.0}  # fmt: skip
    k = score(stressed, P, "market")
    assert k.value == 20 + 20 + 20 + 10 + 8 + 8  # leadership: both ratios falling
    assert score({**CALM, "bank_credit_yoy": 0.11}, P, "fragility").value == 50.0
    assert raw_label(CALM, P) == "CALM"
    assert raw_label(late_cycle, P) == "CAUTION"
    assert raw_label(stressed, P) == "STRESS"
    assert raw_label({**late_cycle, **SHOCK}, P) == "CRISIS"


def test_unknown_signals_add_nothing_and_count_as_missing() -> None:
    market = {*cross_asset.GROUP.columns, *trend.GROUP.columns, *SHOCK}
    no_macro = {k: v for k, v in CALM.items() if k in market}
    m = score(no_macro, P, "macro")
    assert (m.value, m.coverage, m.missing) == (0.0, 0.0, 10)
    assert raw_label(no_macro, P) is None  # never a false CALM
    half = {**no_macro, "curve_10y3m_on": True, "hy_oas_on": False, "nfci_on": False}
    m = score(half, P, "macro")
    assert (m.value, m.coverage, m.missing) == (20.0, 0.55, 7)
    assert raw_label(half, P) == "CALM"  # 55% of the weight known: enough for a label
    assert score({}, P, "fragility").coverage == 0.0


def test_credit_is_the_high_yield_verdict_else_the_excess_bond_premium() -> None:
    no_hy = {k: v for k, v in CALM.items() if k != "hy_oas_on"}
    assert score(no_hy, P, "macro").missing == 1  # neither known: the credit signal is unknown
    assert score({**no_hy, "ebp": 0.006}, P, "macro").value == 20.0  # before 1997: EBP
    assert score({**no_hy, "ebp": 0.004}, P, "macro") == score(CALM, P, "macro")
    assert score({**CALM, "ebp": 0.03}, P, "macro").value == 0.0  # high yield known: it decides


def test_weights_must_sum_to_100() -> None:
    with pytest.raises(ValueError, match="macro weights must sum to 100"):
        Params(w_curve=25.0)
    with pytest.raises(ValueError, match="min_coverage"):
        Params(min_coverage=1.5)


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
    assert (row["macro_risk"], row["macro_coverage"], row["macro_missing"]) == (0.0, 0.0, 10)
    assert pd.isna(row["fragility"])


def write_inputs(by_day: Mapping[date, Mapping[str, object]]) -> object:
    writer, reader = store()
    for g in (macro.GROUP, trend.GROUP, cross_asset.GROUP):
        for d, values in by_day.items():
            write_rows(writer, g.table, d, [{"instrument_id": "MKT:US"} | {
                c: values.get(c) for c in g.columns}])  # fmt: skip
    return writer, reader


def market_inputs(stress_on: date) -> dict[date, dict[str, object]]:
    calm = {"curve_10y3m": 0.01, "curve_inverted_days_252d": 0, "hy_oas": 0.03, "nfci": -0.3,
            "hy_oas_vs_126d_low": 0.0, "unrate_vs_12m_avg": -0.001, "sahm_gap": 0.0,
            "vix_term_ratio": 0.9, "spx_close_vs_sma200": 0.04, **CALM}  # fmt: skip
    shock = {
        **calm,
        "spx_close_vs_sma200": -0.02,
        "vix_term_ratio": 1.2,
        "spx_drawdown_252d": -0.12,
    }
    return {d: (shock if d == stress_on else calm) for d in sessions_ending(END, 15)}


def test_backfill_equals_nightly_and_runs_are_deterministic() -> None:
    days = sessions_ending(END, 15)
    writer, reader = write_inputs(market_inputs(days[9]))  # type: ignore[misc]
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
    # no breadth group stored: breadth unknown, trend + VIX term + drawdown = 50 with 80% known
    assert got == ["STRESS"] * 5 + ["CALM"]


def test_every_regime_column_is_open() -> None:
    """Scores and labels are our own aggregate, never a third-party value (ADR 0047 on 0028)."""
    assert {f.licence for f in regime.GROUP.features} == {"open"}
