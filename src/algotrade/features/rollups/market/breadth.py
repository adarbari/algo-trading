"""``market_breadth@v1``: the cross-section of the session's universe (ADR 0047).

Inputs: ``universe``, the snapshot the session sees (the population: ``None`` before the first
snapshot, when only a later list exists, which would count today's survivors), and ``bars/1d``
(split-adjusted as of the session). Members are the snapshot's stocks (``asset_class``
``STOCK``: common stocks and ADRs); ETFs are left out, so a fund family never counts as
breadth. One ``MKT:US`` row per session.

A member counts towards a column only when its window for that column is complete; a member
without one is never counted as above or below anything. ``universe_coverage`` is the share of
members with a bar on every one of the last 200 sessions (the 200-day average's window). Below
``min_coverage`` (``config/site/rollups.toml``) every breadth column is null and
``breadth_status`` says ``LOW_COVERAGE``; without a universe snapshot everything is null and it
says ``NO_UNIVERSE``.

    pct_above_sma200/50       share of members whose close is above their 200- (50-) session
                              mean close, over members with a complete window
    pct_in_bear               share whose close is more than 20% below their highest close of
                              the last 252 sessions (members with 240+ of those bars)
    new_highs_minus_lows_pct  (members closing at their 252-session closing high - those at
                              their low) / members with 240+ of those bars
    zweig_thrust              the 10-session mean of the advancing share (advancers /
                              (advancers + decliners), close vs the previous close) is above
                              0.615 and was below 0.40 on one of the 10 sessions before
    pct_90_down_days_20d      share of the last 20 sessions where decliners held 90% or more of
                              the dollar volume (close x volume) of advancers and decliners

The advancing share and dollar volumes of earlier sessions count today's members (the snapshot
the session sees), never a later list.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.price.price_stats import Panel, panel

type Matrix = np.ndarray

NAME = "market_breadth"
VERSION = 1
BARS = "bars/1d"
UNIVERSE = "universe"
MEMBER_CLASS = "STOCK"  # the universe's asset class that counts (common stocks and ADRs)
SMA_WINDOWS = (200, 50)
YEAR, MIN_YEAR_BARS = 252, 240  # the 52-week window and the bars a member needs in it
BEAR = 0.20  # more than this far below the 52-week closing high: in a bear market
THRUST_MEAN, THRUST_SPAN, THRUST_LOW, THRUST_HIGH = 10, 10, 0.40, 0.615  # Zweig (1986)
DOWN_DAYS, DOWN_SHARE = 20, 0.90  # Lowry's 90% downside days
LOOKBACK = max(YEAR, THRUST_MEAN + THRUST_SPAN + 1, DOWN_DAYS + 1) - 1

STATUSES = ("OK", "LOW_COVERAGE", "NO_UNIVERSE")
CLOSE, VOLUME = f"{BARS}.close", f"{BARS}.volume"
MEMBERS = f"{UNIVERSE}.instrument_id"
_NULL = (
    "no universe snapshot on or before the session (breadth_status NO_UNIVERSE), or coverage "
    "below min_coverage (LOW_COVERAGE)"
)
_SHARE = (0, 1)


FEATURES = (
    Feature(
        "breadth_status", "str", "category",
        "Whether the breadth columns are computed: OK, LOW_COVERAGE (coverage below "
        "min_coverage: every breadth column null) or NO_UNIVERSE (no universe snapshot on or "
        "before the session: everything null)",
        "never", kind="label", categories=STATUSES, inputs=(MEMBERS, CLOSE),
    ),
    Feature(
        "universe_members", "int", "count",
        "Stocks (common stocks and ADRs) in the universe snapshot the session sees",
        "no universe snapshot on or before the session (NO_UNIVERSE)",
        kind="cross_section", valid_range=(0, None), inputs=(MEMBERS,),
    ),
    Feature(
        "universe_coverage", "float32", "decimal",
        "Share of members with a bar on every one of the last 200 sessions",
        "no universe snapshot on or before the session (NO_UNIVERSE), or it lists no stocks",
        kind="cross_section", valid_range=_SHARE, inputs=(MEMBERS, CLOSE),
    ),
    *(
        Feature(
            f"pct_above_sma{n}", "float32", "decimal",
            f"Share of members whose close is above their mean close over the last {n} sessions "
            f"(over members with a bar on each of those sessions)",
            _NULL, kind="cross_section", valid_range=_SHARE, inputs=(MEMBERS, CLOSE),
        )
        for n in SMA_WINDOWS
    ),
    Feature(
        "pct_in_bear", "float32", "decimal",
        f"Share of members whose close is more than {BEAR:.0%} below their highest close of the "
        f"last {YEAR} sessions (over members with {MIN_YEAR_BARS}+ of those bars)",
        _NULL, kind="cross_section", valid_range=_SHARE, inputs=(MEMBERS, CLOSE),
    ),
    Feature(
        "new_highs_minus_lows_pct", "float32", "decimal",
        f"(Members closing at their highest close of the last {YEAR} sessions - members closing "
        f"at their lowest) / members with {MIN_YEAR_BARS}+ of those bars",
        _NULL, kind="cross_section", valid_range=(-1, 1), inputs=(MEMBERS, CLOSE),
    ),
    Feature(
        "zweig_thrust", "bool", "flag",
        f"Zweig breadth thrust: the {THRUST_MEAN}-session mean of the advancing share "
        f"(advancers / (advancers + decliners)) is above {THRUST_HIGH} and was below "
        f"{THRUST_LOW} on one of the {THRUST_SPAN} sessions before",
        f"{_NULL}; or a session among the last {THRUST_MEAN + THRUST_SPAN} had no member "
        "advance or decline",
        kind="cross_section", inputs=(MEMBERS, CLOSE),
    ),
    Feature(
        "pct_90_down_days_20d", "float32", "decimal",
        f"Share of the last {DOWN_DAYS} sessions on which decliners held {DOWN_SHARE:.0%} or more "
        "of the dollar volume (close x volume) of advancers and decliners",
        f"{_NULL}; or a session among the last {DOWN_DAYS} had no member dollar volume up or down",
        kind="cross_section", valid_range=_SHARE, inputs=(MEMBERS, CLOSE, VOLUME),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class MarketBreadthParams:
    min_coverage: float = 0.8  # below this share of members with bars, breadth is null

    def __post_init__(self) -> None:
        if not 0 <= self.min_coverage <= 1:
            raise ValueError(f"min_coverage must be in [0, 1], got {self.min_coverage}")


def _share(hits: np.ndarray, eligible: np.ndarray) -> float:
    n = int(eligible.sum())
    return float((hits & eligible).sum() / n) if n else np.nan


def _advance_decline(close: Matrix) -> tuple[Matrix, Matrix]:
    """Per session (from the second): which members advanced / declined vs the previous close."""
    now, before = close[1:], close[:-1]
    both = ~np.isnan(now) & ~np.isnan(before)
    with np.errstate(invalid="ignore"):
        return both & (now > before), both & (now < before)


def thrust(close: Matrix) -> bool | None:
    """The Zweig breadth thrust on the last session; ``None`` when a session in its span had no
    advancer or decliner."""
    up, down = _advance_decline(close[-(THRUST_MEAN + THRUST_SPAN + 1) :])
    moved = up.sum(axis=1) + down.sum(axis=1)
    if (moved == 0).any():
        return None
    share = up.sum(axis=1) / moved
    mean = np.convolve(share, np.ones(THRUST_MEAN) / THRUST_MEAN, mode="valid")
    return bool(mean[-1] > THRUST_HIGH and mean[:-1].min() < THRUST_LOW)


def down_days(close: Matrix, volume: Matrix) -> float:
    """Share of the last ``DOWN_DAYS`` sessions that were 90% downside days (NaN: a session with
    no dollar volume up or down)."""
    window = slice(-(DOWN_DAYS + 1), None)
    up, down = _advance_decline(close[window])
    dollars = np.nan_to_num(close[window] * volume[window])[1:]
    up_usd, down_usd = (dollars * up).sum(axis=1), (dollars * down).sum(axis=1)
    total = up_usd + down_usd
    if (total == 0).any():
        return np.nan
    return float((down_usd / total >= DOWN_SHARE).mean())


def breadth(px: Panel) -> dict[str, object]:
    """The breadth columns for the LAST session over the panel's instruments (the members)."""
    close = px.close
    last = close[-1]
    out: dict[str, object] = {}
    with np.errstate(invalid="ignore"):
        for n in SMA_WINDOWS:
            window = close[-n:]
            complete = ~np.isnan(window).any(axis=0)
            out[f"pct_above_sma{n}"] = _share(last > window.mean(axis=0), complete)
        year = close[-YEAR:]
        enough = ((~np.isnan(year)).sum(axis=0) >= MIN_YEAR_BARS) & ~np.isnan(last)
        high, low = np.fmax.reduce(year, axis=0), np.fmin.reduce(year, axis=0)
        out["pct_in_bear"] = _share(last < (1 - BEAR) * high, enough)
        n = int(enough.sum())
        highs, lows = int((enough & (last >= high)).sum()), int((enough & (last <= low)).sum())
    out["new_highs_minus_lows_pct"] = (highs - lows) / n if n else np.nan
    out["zweig_thrust"] = thrust(close)
    out["pct_90_down_days_20d"] = down_days(close, px.volume)
    return out


def _row(
    universe: pd.DataFrame | None, bars: pd.DataFrame, session: date, p: MarketBreadthParams
) -> dict[str, object]:
    if universe is None:
        return {"breadth_status": "NO_UNIVERSE"}
    members = universe.loc[universe["asset_class"] == MEMBER_CLASS, "instrument_id"].unique()
    mine = bars[bars["instrument_id"].isin(members)]
    if mine.empty:
        coverage = 0.0 if len(members) else None
        return {
            "breadth_status": "LOW_COVERAGE",
            "universe_members": len(members),
            "universe_coverage": coverage,
        }
    px = panel(mine, sessions_ending(session, LOOKBACK + 1))
    covered = int((~np.isnan(px.close[-SMA_WINDOWS[0] :]).any(axis=0)).sum())
    row: dict[str, object] = {
        "universe_members": len(members),
        "universe_coverage": covered / len(members),
    }
    if covered / len(members) < p.min_coverage:
        return {**row, "breadth_status": "LOW_COVERAGE"}
    return {**row, **breadth(px), "breadth_status": "OK"}


def compute(inputs: Inputs, session: date, p: MarketBreadthParams) -> pd.DataFrame:
    bars = inputs[BARS]
    assert bars is not None  # required input
    row = {"instrument_id": market_id("US"), **_row(inputs[UNIVERSE], bars, session, p)}
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Breadth of the session's universe (stocks): shares above the 200- and 50-day averages "
    "and in a bear market, new highs minus lows, the Zweig thrust and 90% down days",
    (Input(BARS, lookback=LOOKBACK), Input(UNIVERSE, required=False)),
    FEATURES,
    compute,
    MarketBreadthParams(),
    entity="market",
)
