"""``regime_indicators@v1``: the regime cards' readings, one ``MKT:US`` row per session (ADR
0047; the contract of ``services/read/regime/fields.py`` and ``config/site/regime/cards.toml``).

For each card ``CARDS`` key: ``<key>`` its value (a column of ``market_macro@v1``,
``market_trend@v1`` or ``market_breadth@v1`` for the session), ``<key>_on`` its verdict from the
thresholds of ``Params`` (``config/site/rollups.toml ["regime_indicators@v1"]``), and
``<key>_changed`` whether that verdict differs from the one ``changed_sessions`` sessions
earlier. The earlier verdict is recomputed from the inputs stored for that session, never read
back from this group (stateless: a backfill equals the nightly).

A verdict is null (UNKNOWN) when a value it needs is null; an "either" rule (the high-yield
spread) is on as soon as one side is on. ``_changed`` is null unless both verdicts are known.
The expression language has no look-back across sessions, so the verdicts live here, not in
``config/site/features/regime.toml``.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.market import breadth, macro, trend

NAME = "regime_indicators"
VERSION = 1
type Values = Mapping[str, object]  # one session's columns of the input groups, by column
type Verdict = bool | None


@dataclass(frozen=True)
class Params:
    """The cards' thresholds (docs/market-regime-plan.md sections 3 and 4)."""

    changed_sessions: int = 5  # <key>_changed compares with this many sessions earlier
    curve_min_inverted_days: int = 21  # curve: inverted now and on this many of the last 252
    hy_oas_above: float = 0.05  # high-yield spread above 5% ...
    hy_oas_off_low: float = 0.015  # ... or 150 bp or more above its 6-month low
    unrate_trend_above: float = 0.0  # unemployment above its 12-month mean
    sahm_at_least: float = 0.005  # the Sahm rule's 0.5 point
    nfci_above: float = 0.0  # financial conditions tighter than average
    spx_trend_below: float = 0.0  # SPY below its 200-day mean
    vix_term_above: float = 1.0  # VIX above VIX3M (backwardation)
    breadth_below: float = 0.40  # fewer than 40% of the universe above their 200-day mean

    def __post_init__(self) -> None:
        if self.changed_sessions < 1:
            raise ValueError(f"changed_sessions must be >= 1, got {self.changed_sessions}")
        if self.curve_min_inverted_days < 0:
            raise ValueError("curve_min_inverted_days must be >= 0")


def number(v: Values, column: str) -> float:
    """A number column of ``v`` (NaN: null or missing)."""
    value = v.get(column)
    return float(value) if isinstance(value, (int, float, np.number)) else np.nan


def compare(value: float, op: str, threshold: float) -> Verdict:
    """``value op threshold`` (``>``, ``>=``, ``<``, ``<=``); ``None`` when ``value`` is null.
    Compared as 32-bit floats, the type the inputs are stored as, so a value stored exactly at
    a threshold (a 5.00% spread) sits on it rather than a rounding error above or below."""
    if np.isnan(value):
        return None
    v, t = np.float32(value), np.float32(threshold)
    ops = {">": v > t, ">=": v >= t, "<": v < t, "<=": v <= t}
    return bool(ops[op])


def either(*verdicts: Verdict) -> Verdict:
    """On when one is on; off when all are off; else unknown (Kleene or)."""
    if any(v is True for v in verdicts):
        return True
    return None if any(v is None for v in verdicts) else False


def both(*verdicts: Verdict) -> Verdict:
    """Off when one is off; on when all are on; else unknown (Kleene and)."""
    if any(v is False for v in verdicts):
        return False
    return None if any(v is None for v in verdicts) else True


@dataclass(frozen=True)
class Card:
    key: str
    group: str  # the input group's key
    column: str  # its value column
    rule: str  # the verdict in words (the feature's description)
    verdict: Callable[[Values, Params], Verdict]


def _curve(v: Values, p: Params) -> Verdict:
    days = number(v, "curve_inverted_days_252d")
    return both(compare(number(v, "curve_10y3m"), "<", 0.0),
                compare(days, ">=", p.curve_min_inverted_days))  # fmt: skip


def _hy(v: Values, p: Params) -> Verdict:
    return either(compare(number(v, "hy_oas"), ">", p.hy_oas_above),
                  compare(number(v, "hy_oas_vs_126d_low"), ">=", p.hy_oas_off_low))  # fmt: skip


D = Params()
M, T, B = macro.GROUP.key, trend.GROUP.key, breadth.GROUP.key
CARDS = (
    Card("curve_10y3m", M, "curve_10y3m",
         f"10y - 3m below 0 now and on at least {D.curve_min_inverted_days} of the last 252 "
         "sessions (inverted for about a month)", _curve),
    Card("hy_oas", M, "hy_oas", f"high-yield spread above {D.hy_oas_above:.0%}, or "
         f"{D.hy_oas_off_low * 1e4:.0f} bp or more above its 126-session low", _hy),
    Card("unrate_trend", M, "unrate_vs_12m_avg", "unemployment above its 12-month mean",
         lambda v, p: compare(number(v, "unrate_vs_12m_avg"), ">", p.unrate_trend_above)),
    Card("sahm", M, "sahm_gap", f"Sahm gap at least {D.sahm_at_least * 100:.1f} points",
         lambda v, p: compare(number(v, "sahm_gap"), ">=", p.sahm_at_least)),
    Card("nfci", M, "nfci", "NFCI above 0 (tighter than average)",
         lambda v, p: compare(number(v, "nfci"), ">", p.nfci_above)),
    Card("spx_trend_200d", T, "spx_close_vs_sma200", "SPY below its 200-day mean",
         lambda v, p: compare(number(v, "spx_close_vs_sma200"), "<", p.spx_trend_below)),
    Card("vix_term", M, "vix_term_ratio", f"VIX / VIX3M above {D.vix_term_above:g}",
         lambda v, p: compare(number(v, "vix_term_ratio"), ">", p.vix_term_above)),
    Card("breadth_200d", B, "pct_above_sma200",
         f"fewer than {D.breadth_below:.0%} of the universe above their 200-day mean",
         lambda v, p: compare(number(v, "pct_above_sma200"), "<", p.breadth_below)),
)  # fmt: skip
GROUPS = {g.key: g for g in (macro.GROUP, trend.GROUP, breadth.GROUP)}
# What each card's verdict reads, beyond its value column.
EXTRA = {"curve_10y3m": ("curve_inverted_days_252d",), "hy_oas": ("hy_oas_vs_126d_low",)}


def _features(c: Card) -> tuple[Feature, ...]:
    source = GROUPS[c.group].feature(c.column)
    group = GROUPS[c.group]
    reads = tuple(group.feature(col).key for col in (c.column, *EXTRA.get(c.key, ())))
    licence: Licence = source.licence
    unknown = f"{source.key} is null for the session"
    return (
        Feature(c.key, "float32", source.unit, f"{source.description} (the {c.key} card's value)",
                unknown, valid_range=source.valid_range, inputs=(source.key,), licence=licence),
        Feature(f"{c.key}_on", "bool", "flag", f"The {c.key} card is on: {c.rule}",
                f"a value the rule needs is null ({', '.join(reads)})", inputs=reads,
                licence=licence),
        Feature(f"{c.key}_changed", "bool", "flag", f"The {c.key} verdict differs from "
                f"{D.changed_sessions} sessions earlier (recomputed from that session's inputs)",
                "the verdict now or then is null", inputs=reads, licence=licence),
    )  # fmt: skip


FEATURES = tuple(f for card in CARDS for f in _features(card))
COLUMNS = column_types(FEATURES)


def session_values(inputs: Inputs, day: date) -> dict[str, object]:
    """The columns of every input group's row for ``day`` (later inputs win on a shared name;
    none share one), empty when no input has a row for it."""
    out: dict[str, object] = {}
    for frame in inputs.values():
        if frame is None or frame.empty or "session_date" not in frame.columns:
            continue
        rows = frame[pd.to_datetime(frame["session_date"]).dt.date == day]
        if len(rows):
            row = rows.iloc[-1].drop(labels=["instrument_id", "session_date"], errors="ignore")
            out.update({str(k): value for k, value in row.items()})
    return out


def verdicts(v: Values, p: Params) -> dict[str, Verdict]:
    return {c.key: c.verdict(v, p) for c in CARDS}


def compute(inputs: Inputs, session: date, params: Params) -> pd.DataFrame:
    then = sessions_ending(session, params.changed_sessions + 1)[0]
    now_v = session_values(inputs, session)
    now, before = verdicts(now_v, params), verdicts(session_values(inputs, then), params)
    row: dict[str, object] = {"instrument_id": market_id("US")}
    for c in CARDS:
        row[c.key] = number(now_v, c.column)
        row[f"{c.key}_on"] = now[c.key]
        known = now[c.key] is not None and before[c.key] is not None
        row[f"{c.key}_changed"] = now[c.key] != before[c.key] if known else None
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


def _lookback(p: Params) -> int:
    return p.changed_sessions


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The regime cards' readings: each indicator's value, its on / off verdict from the site's "
    "thresholds and whether the verdict changed within 5 sessions",
    tuple(Input(g.table, lookback=_lookback, required=False) for g in GROUPS.values()),
    FEATURES,
    compute,
    params=D,
    entity="market",
)
