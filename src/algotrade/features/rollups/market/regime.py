"""``regime@v2``: the regime model's two scores, its context score and its label, one ``MKT:US``
row per session (ADR 0047; docs/market-regime-plan.md section 4).

Each score is a weighted count of signals that are on (``SIGNALS``; weights and thresholds in
``Params``, ``config/site/rollups.toml ["regime@v2"]``, each score's weights summing to 100).
The cards' signals are ``regime_indicators@v1``'s verdicts; the others are thresholds on
``market_macro@v3``, ``market_trend@v2`` and ``market_cross_asset@v1`` here.

- ``macro_risk`` (slow): curve, credit (the high-yield card's verdict, else, when the high-yield
  spread is unknown, as before 1997, the excess bond premium above ``ebp_above``), labour
  (unemployment trend, Sahm, claims), financial conditions, lending standards, permits, Fed
  hikes and inflation.
- ``market_stress`` (fast): trend, VIX term structure, drawdown, breadth, leadership and credit
  ETFs, turbulence and absorption.
- ``fragility`` (context only, never the label): credit expansion and the index's one-year
  run-up (CAPE and margin debt are not stored yet); null when neither is known.

A signal whose inputs are null counts in ``<score>_missing``; ``<score>_coverage`` is the share
of the score's weight that is known. ``macro_risk`` and ``market_stress`` are on the
covered-weight scale: ``100 * on weight / known weight``, so a signal that cannot be computed
yet (its window is longer than the stored bars) neither adds nor dilutes; null (UNKNOWN) when
the coverage is below ``min_coverage``. ``<score>_raw`` keeps the unnormalised weight on (an
unknown signal adds 0). ``raw_label`` is CALM (neither score high), CAUTION (macro only), STRESS
(market only) or CRISIS (both), and null (UNKNOWN) when either score is: no data never reads
CALM. ``label`` is the most severe known ``raw_label`` of the last ``hold_sessions`` sessions
(null when the session's own is), so a regime is left only after that many sessions below it;
it is recomputed from the inputs of those sessions, never from this group's earlier rows
(stateless: a backfill equals the nightly). ``label_changed``: the label differs from
``changed_sessions`` sessions earlier.

Every column is open (ADR 0047, on ADR 0028): the scores and labels are our own aggregate of
verdicts, never a third-party value.

v2 moved the two scores to the covered-weight scale and added ``macro_risk_raw`` and
``market_stress_raw`` (v1's scores, in which an unknown signal counted as off, so a young
history read calm however many of its known signals were on). v1 is superseded but not in
``features.registry.SUPERSEDED``: that map, ``moved_field`` and ``retire-features`` handle
instrument groups only (``rollup.`` fields, ``rollups/instrument/`` tables); nothing reads
``rollups/market/regime@v1`` (every read names ``regime@v2``), and its table is deleted by hand
once v2 is backfilled.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.market import cross_asset, indicators, macro, trend
from algotrade.features.rollups.market.indicators import (
    Values,
    Verdict,
    both,
    compare,
    number,
    session_values,
)

NAME = "regime"
VERSION = 2
LABELS = ("CALM", "CAUTION", "STRESS", "CRISIS")  # least to most severe
type Score = Literal["macro", "market", "fragility"]
SCORES: tuple[Score, ...] = ("macro", "market", "fragility")


@dataclass(frozen=True)
class Params:
    """Weights (``w_*``: each score's sum to 100) and thresholds of the regime model (the
    plan's starting values, to be tuned on the episode scorecard)."""

    hold_sessions: int = 5  # the label is the most severe raw label of this many sessions
    changed_sessions: int = 5  # label_changed compares with this many sessions earlier
    min_coverage: float = 0.5  # below this share of known weight a score gives no label
    macro_high: float = 50.0  # macro_risk at or above: high
    market_high: float = 50.0  # market_stress at or above: high
    # macro_risk: curve 20, credit 20, labour 20, NFCI 15, lending 10, permits 5, Fed + CPI 10
    w_curve: float = 20.0
    w_credit: float = 20.0
    w_unrate_trend: float = 7.0
    w_sahm: float = 7.0
    w_claims: float = 6.0
    w_nfci: float = 15.0
    w_sloos: float = 10.0
    w_permits: float = 5.0
    w_fed: float = 5.0
    w_inflation: float = 5.0
    claims_at_least: float = 1.15  # 4-week claims 15% or more above their 52-week low
    sloos_above: float = 0.20  # more than 20% of banks tightening
    permits_at_most: float = -0.20  # permits down 20% or more on the year
    fed_hikes_above: float = 0.02  # fed funds up more than 200 bp on the year
    cpi_above: float = 0.04  # CPI inflation above 4%
    ebp_above: float = 0.005  # credit, when the high-yield spread is unknown: EBP above 50 bp
    # market_stress: trend 20, VIX term 20, drawdown 10, breadth 20, leadership + credit 15,
    # turbulence + absorption 15
    w_trend: float = 20.0
    w_vol_term: float = 20.0
    w_drawdown: float = 10.0
    w_breadth: float = 20.0
    w_leadership: float = 8.0
    w_credit_etf: float = 7.0
    w_turbulence: float = 8.0
    w_absorption: float = 7.0
    drawdown_at_most: float = -0.10  # SPY 10% or more below its 52-week closing high
    turbulence_at_least: float = 2.0  # turbulence / basket size (about 1 on an ordinary day)
    absorption_shift_at_least: float = 1.0  # absorption up a standard deviation
    # fragility
    w_credit_boom: float = 50.0
    w_runup: float = 50.0
    credit_boom_above: float = 0.10  # bank credit up more than 10% on the year
    runup_above: float = 0.30  # SPY up more than 30% on the year

    def __post_init__(self) -> None:
        if self.hold_sessions < 1 or self.changed_sessions < 1:
            raise ValueError("hold_sessions and changed_sessions must be >= 1")
        if not 0.0 <= self.min_coverage <= 1.0:
            raise ValueError(f"min_coverage must be in [0, 1], got {self.min_coverage}")
        weights = [f.name for f in fields(self) if f.name.startswith("w_")]
        if any(getattr(self, w) < 0 for w in weights):
            raise ValueError("weights must be >= 0")
        for score in SCORES:
            total = sum(getattr(self, s.weight) for s in SIGNALS if s.score == score)
            if abs(total - 100.0) > 1e-9:
                raise ValueError(f"the {score} weights must sum to 100, got {total:g}")


def flag(v: Values, column: str) -> Verdict:
    """A stored verdict (an indicator's ``<key>_on``) or ``None``."""
    value = v.get(column)
    return bool(value) if isinstance(value, (bool, np.bool_)) else None


def _credit(v: Values, p: Params) -> Verdict:
    """The high-yield card's verdict; when it is unknown, the excess bond premium's."""
    high_yield = flag(v, "hy_oas_on")
    return high_yield if high_yield is not None else compare(number(v, "ebp"), ">", p.ebp_above)


def _turbulence(v: Values, p: Params) -> Verdict:
    size = number(v, "basket_size")
    ratio = number(v, "turbulence_60d") / size if size else np.nan
    return compare(ratio, ">=", p.turbulence_at_least)


@dataclass(frozen=True)
class Signal:
    name: str
    score: Score
    weight: str  # its ``Params`` weight field
    reads: tuple[str, ...]  # the feature keys of the columns it reads
    verdict: Callable[[Values, Params], Verdict]


def _keys(group: str, *columns: str) -> tuple[str, ...]:
    g = GROUPS[group]
    return tuple(g.feature(c).key for c in columns)


GROUPS = {g.key: g for g in (indicators.GROUP, macro.GROUP, trend.GROUP, cross_asset.GROUP)}
CARD, M, T, X = indicators.GROUP.key, macro.GROUP.key, trend.GROUP.key, cross_asset.GROUP.key


def _card(name: str, score: Score, weight: str, key: str) -> Signal:
    return Signal(name, score, weight, _keys(CARD, f"{key}_on"), lambda v, p: flag(v, f"{key}_on"))


def _over(
    name: str, score: Score, weight: str, group: str, column: str, op: str, at: str
) -> Signal:
    return Signal(name, score, weight, _keys(group, column),
                  lambda v, p: compare(number(v, column), op, getattr(p, at)))  # fmt: skip


SIGNALS: tuple[Signal, ...] = (
    _card("curve", "macro", "w_curve", "curve_10y3m"),
    Signal("credit", "macro", "w_credit", (*_keys(CARD, "hy_oas_on"), *_keys(M, "ebp")), _credit),
    _card("unrate_trend", "macro", "w_unrate_trend", "unrate_trend"),
    _card("sahm", "macro", "w_sahm", "sahm"),
    _over("claims", "macro", "w_claims", M, "claims_4w_vs_52w_low", ">=", "claims_at_least"),
    _card("nfci", "macro", "w_nfci", "nfci"),
    _over("sloos", "macro", "w_sloos", M, "sloos_ci_tightening", ">", "sloos_above"),
    _over("permits", "macro", "w_permits", M, "permits_yoy", "<=", "permits_at_most"),
    _over("fed", "macro", "w_fed", M, "fedfunds_chg_12m", ">", "fed_hikes_above"),
    _over("inflation", "macro", "w_inflation", M, "cpi_yoy", ">", "cpi_above"),
    _card("trend", "market", "w_trend", "spx_trend_200d"),
    _card("vol_term", "market", "w_vol_term", "vix_term"),
    _over("drawdown", "market", "w_drawdown", T, "spx_drawdown_252d", "<=", "drawdown_at_most"),
    _card("breadth", "market", "w_breadth", "breadth_200d"),
    Signal("leadership", "market", "w_leadership", _keys(X, "xly_vs_xlp", "iwm_vs_spy"),
           lambda v, p: both(compare(number(v, "xly_vs_xlp"), "<", 0.0),
                             compare(number(v, "iwm_vs_spy"), "<", 0.0))),
    Signal("credit_etf", "market", "w_credit_etf", _keys(X, "hyg_vs_lqd"),
           lambda v, p: compare(number(v, "hyg_vs_lqd"), "<", 0.0)),
    Signal("turbulence", "market", "w_turbulence", _keys(X, "turbulence_60d", "basket_size"),
           _turbulence),
    _over("absorption", "market", "w_absorption", X, "absorption_shift", ">=",
          "absorption_shift_at_least"),
    _over("credit_boom", "fragility", "w_credit_boom", M, "bank_credit_yoy", ">",
          "credit_boom_above"),
    _over("runup", "fragility", "w_runup", T, "spx_ret_252d", ">", "runup_above"),
)  # fmt: skip


@dataclass(frozen=True)
class Scored:
    """One score: ``raw`` the weight of its signals on (an unknown signal adds 0), ``known``
    the weight of its signals known, ``coverage`` the share of its weight known, ``missing``
    how many of its signals are unknown."""

    raw: float
    known: float
    coverage: float
    missing: int

    def scaled(self, min_coverage: float) -> float:
        """The covered-weight scale, 0 to 100: the weight on over the weight known; NaN when
        less than ``min_coverage`` of the weight is known."""
        if self.known <= 0.0 or self.coverage < min_coverage:
            return np.nan
        return 100.0 * self.raw / self.known


def score(v: Values, p: Params, which: Score) -> Scored:
    total = known = on = 0.0
    missing = 0
    for s in (s for s in SIGNALS if s.score == which):
        weight = getattr(p, s.weight)
        total += weight
        verdict = s.verdict(v, p)
        if verdict is None:
            missing += 1
            continue
        known += weight
        on += weight if verdict else 0.0
    return Scored(on, known, known / total if total else 0.0, missing)


def raw_label(v: Values, p: Params) -> str | None:
    """The session's label before hysteresis, from the covered-weight scores; ``None`` when a
    score's coverage is too low."""
    macro_risk = score(v, p, "macro").scaled(p.min_coverage)
    stress = score(v, p, "market").scaled(p.min_coverage)
    if np.isnan(macro_risk) or np.isnan(stress):
        return None
    return LABELS[2 * (stress >= p.market_high) + (macro_risk >= p.macro_high)]


def held(raws: Mapping[date, str | None], day: date, hold: int) -> str | None:
    """The most severe known raw label of the ``hold`` sessions ending ``day`` (``None`` when
    ``day``'s own is unknown)."""
    if raws.get(day) is None:
        return None
    known = [label for d in sessions_ending(day, hold) if (label := raws.get(d)) is not None]
    return max(known, key=LABELS.index)


def compute(inputs: Inputs, session: date, params: Params) -> pd.DataFrame:
    p = params
    days = sessions_ending(session, p.hold_sessions + p.changed_sessions)
    raws = {d: raw_label(session_values(inputs, d), p) for d in days}
    v = session_values(inputs, session)
    m, k, f = (score(v, p, s) for s in SCORES)
    label = held(raws, session, p.hold_sessions)
    before = held(raws, days[-1 - p.changed_sessions], p.hold_sessions)
    row = {
        "instrument_id": market_id("US"),
        "label": label,
        "raw_label": raws[session],
        "macro_risk": m.scaled(p.min_coverage),
        "market_stress": k.scaled(p.min_coverage),
        "macro_risk_raw": m.raw,
        "market_stress_raw": k.raw,
        "fragility": f.raw if f.coverage > 0 else np.nan,
        "macro_coverage": m.coverage,
        "market_coverage": k.coverage,
        "macro_missing": m.missing,
        "market_missing": k.missing,
        "label_changed": None if label is None or before is None else label != before,
    }
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


def _reads(which: Score | None = None) -> tuple[str, ...]:
    keys = (r for s in SIGNALS if which is None or s.score == which for r in s.reads)
    return tuple(dict.fromkeys(keys))


D = Params()
_SCORE_READS = _reads("macro") + _reads("market")


def _weights(which: Score) -> str:
    return ", ".join(f"{s.name} {getattr(D, s.weight):g}" for s in SIGNALS if s.score == which)


def _score(name: str, which: Score, words: str) -> tuple[Feature, ...]:
    reads = _reads(which)
    return (
        Feature(name, "float32", "pct_points", f"{words} on the covered-weight scale: the "
                f"weight of its signals that are on over the weight of those known, 0 to 100 "
                f"(weights {_weights(which)}); an unknown signal neither adds nor dilutes",
                f"less than min_coverage ({D.min_coverage:g}) of its weight is known",
                valid_range=(0, 100), inputs=reads),
        Feature(f"{name}_raw", "float32", "pct_points", f"{words}, unnormalised: the weight of "
                "its signals that are on, 0 to 100, an unknown signal adding 0 (the scale of "
                "regime@v1)", "never: an unknown signal adds 0 (see the coverage)",
                valid_range=(0, 100), inputs=reads),
        Feature(f"{which}_coverage", "float32", "decimal", f"Share of {name}'s weight whose "
                "signals are known (below min_coverage, 0.5: no label)", "never",
                valid_range=(0, 1), inputs=reads),
        Feature(f"{which}_missing", "int", "count", f"How many of {name}'s signals are "
                "unknown (an input is null)", "never", valid_range=(0, 20), inputs=reads),
    )  # fmt: skip


_UNKNOWN = (
    f"a score's coverage is below min_coverage ({D.min_coverage:g}): its inputs are not known "
    "(no FRED data, or a market group missing)"
)
FEATURES = (
    Feature("label", "str", "category", f"The market regime: the most severe raw_label of the "
            f"last {D.hold_sessions} sessions (CALM, CAUTION: macro risk high, STRESS: market "
            "stress high, CRISIS: both), so a regime is left only after that many calmer "
            "sessions", f"the session's raw_label is unknown: {_UNKNOWN}", kind="label",
            categories=LABELS, inputs=_SCORE_READS),
    Feature("raw_label", "str", "category", f"The session's regime before hysteresis: "
            f"macro_risk >= {D.macro_high:g} is macro high, market_stress >= {D.market_high:g} "
            "market high; CALM neither, CAUTION macro only, STRESS market only, CRISIS both",
            _UNKNOWN, kind="label", categories=LABELS, inputs=_SCORE_READS),
    *_score("macro_risk", "macro", "Slow macro recession risk"),
    *_score("market_stress", "market", "Fast market stress"),
    Feature("fragility", "float32", "pct_points", f"Context only (never the label): how deep a "
            f"fall could be, the weight of its signals on, 0 to 100 ({_weights('fragility')}: "
            f"bank credit up more than {D.credit_boom_above:.0%} on the year, SPY up more than "
            f"{D.runup_above:.0%} on the year)", "neither bank credit growth nor SPY's one-year "
            "return is known", valid_range=(0, 100), inputs=_reads("fragility")),
    Feature("label_changed", "bool", "flag", f"The label differs from {D.changed_sessions} "
            "sessions earlier", "the label now or then is unknown", inputs=_SCORE_READS),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _lookback(p: Params) -> int:
    return p.hold_sessions + p.changed_sessions - 1


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The market regime: macro risk and market stress scores (weighted counts of signals on), "
    "the fragility context score and the label with its 5-session hold",
    tuple(Input(g.table, lookback=_lookback, required=False) for g in GROUPS.values()),
    FEATURES,
    compute,
    params=D,
    entity="market",
)
