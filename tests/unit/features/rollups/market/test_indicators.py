"""``regime_indicators@v1``: each card's verdict on either side of its threshold, Kleene
nulls, and ``_changed`` against the verdict recomputed for 5 sessions earlier."""

from collections.abc import Mapping
from datetime import date

import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.rollups.market import breadth, indicators, macro, trend
from algotrade.features.rollups.market.indicators import CARDS, Params, verdicts
from tests.helpers.rollup_store import END

P = Params()
CALM: dict[str, object] = {
    "curve_10y3m": 0.01, "curve_inverted_days_252d": 0, "hy_oas": 0.035,
    "hy_oas_vs_126d_low": 0.002, "unrate_vs_12m_avg": -0.001, "sahm_gap": 0.001, "nfci": -0.4,
    "spx_close_vs_sma200": 0.05, "vix_term_ratio": 0.85, "pct_above_sma200": 0.6,
}  # fmt: skip


def verdict(card: str, **changes: object) -> bool | None:
    return verdicts({**CALM, **changes}, P)[card]


@pytest.mark.parametrize(
    ("card", "column", "off", "on"),
    [
        ("hy_oas", "hy_oas", 0.05, 0.0501),  # above 5%
        ("hy_oas", "hy_oas_vs_126d_low", 0.0149, 0.015),  # 150 bp off the low or more
        ("unrate_trend", "unrate_vs_12m_avg", 0.0, 0.0001),
        ("sahm", "sahm_gap", 0.0049, 0.005),
        ("nfci", "nfci", 0.0, 0.01),
        ("spx_trend_200d", "spx_close_vs_sma200", 0.0, -0.0001),
        ("vix_term", "vix_term_ratio", 1.0, 1.0001),
        ("breadth_200d", "pct_above_sma200", 0.40, 0.3999),
    ],
)
def test_each_verdict_at_its_boundary(card: str, column: str, off: float, on: float) -> None:
    assert verdict(card, **{column: off}) is False
    assert verdict(card, **{column: on}) is True
    assert verdict(card) is False


def test_the_curve_is_on_only_when_inverted_for_about_a_month() -> None:
    assert verdict("curve_10y3m", curve_10y3m=-0.001, curve_inverted_days_252d=21) is True
    assert verdict("curve_10y3m", curve_10y3m=-0.001, curve_inverted_days_252d=20) is False
    assert verdict("curve_10y3m", curve_10y3m=0.0, curve_inverted_days_252d=200) is False
    assert verdict("curve_10y3m", curve_10y3m=-0.001, curve_inverted_days_252d=None) is None
    assert verdict("curve_10y3m", curve_10y3m=0.001, curve_inverted_days_252d=None) is False


def test_a_null_input_is_unknown_unless_the_other_side_decides() -> None:
    assert verdict("nfci", nfci=None) is None
    assert verdict("hy_oas", hy_oas=0.06, hy_oas_vs_126d_low=None) is True  # either side on
    assert verdict("hy_oas", hy_oas=0.04, hy_oas_vs_126d_low=None) is None
    assert verdicts({}, P) == {c.key: None for c in CARDS}


def frames(by_day: Mapping[date, Mapping[str, object]]) -> dict[str, pd.DataFrame | None]:
    """Each input group's rows for these sessions, from one flat dict of columns per day."""
    out: dict[str, pd.DataFrame | None] = {}
    for g in (macro.GROUP, trend.GROUP, breadth.GROUP):
        rows = [
            {"instrument_id": "MKT:US", "session_date": d}
            | {c: v for c, v in values.items() if c in g.columns}
            for d, values in sorted(by_day.items())
        ]
        out[g.table] = pd.DataFrame(rows)
    return out


def test_the_row_copies_values_and_changed_compares_with_5_sessions_earlier() -> None:
    days = sessions_ending(END, 6)
    by_day = {d: dict(CALM) for d in days}
    by_day[END] = {**CALM, "nfci": 0.2, "pct_above_sma200": None}
    row = indicators.compute(frames(by_day), END, P).iloc[0]
    assert row["nfci"] == 0.2 and bool(row["nfci_on"]) and bool(row["nfci_changed"])
    assert not row["sahm_on"] and not row["sahm_changed"]
    assert pd.isna(row["breadth_200d"]) and row["breadth_200d_on"] is None
    assert row["breadth_200d_changed"] is None
    del by_day[days[0]]  # nothing stored 5 sessions earlier: changed is unknown
    row = indicators.compute(frames(by_day), END, P).iloc[0]
    assert bool(row["nfci_on"]) and row["nfci_changed"] is None


def test_the_contract_columns_of_the_read_model() -> None:
    keys = ["curve_10y3m", "hy_oas", "unrate_trend", "sahm", "nfci", "spx_trend_200d",
            "vix_term", "breadth_200d"]  # fmt: skip
    assert [c.key for c in CARDS] == keys
    assert list(indicators.COLUMNS) == [f"{k}{s}" for k in keys for s in ("", "_on", "_changed")]
    assert indicators.GROUP.key == "regime_indicators@v1" and indicators.GROUP.entity == "market"
    personal = {f.name for f in indicators.FEATURES if f.licence == "personal"}
    assert personal == {f"{k}{s}" for k in ("hy_oas", "vix_term") for s in ("", "_on", "_changed")}
