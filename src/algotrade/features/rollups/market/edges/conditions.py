"""``market_conditions@v2``: the market a setup enters, one ``MKT:US`` row per session (ADR 0088,
design section 2.1): the VIX-family statistics, the dimension states D1-D11 as open ``_on``
verdicts, the stand-aside verdict ``short_premium_allowed``, the 10-year yield change, the
share of the universe about to report and the calendar distances. A **leaf** group: nothing in
the headline regime reads it, so ``regime@v3`` and its fingerprint are untouched. Which of these
a setup gates or slices on is the setup's own choice (a rule over catalogue features); none is
shared by default.

Inputs: ``macro/series`` VIX, VIX3M, VIX9D, VIX6M and VVIX (Cboe closes, ``pit = "lag"``,
``release_lag_days = 1``: personal use only), the stored ``market_trend@v2`` and
``regime_indicators@v1`` rows, ``rates/treasury_10y``, ``events/macro_release`` (FOMC) and
``earnings_expected@v1``.

Point in time. A VIX-family value is the latest observation known by the session; the shared
observation date ``vix_obs_date`` is the VIX's, and a series that has no observation on that
exact date is null (a ratio of two series is never taken across dates, never filled); the
S&P 500 trend and realised volatility are read from the ``market_trend@v2`` row dated
``vix_obs_date``, never the session's own, so the VIX and the index describe the same close.
Stale is null: when the newest VIX observation is more than ``MAX_AGE_SESSIONS`` old every
VIX-derived column is null. The rate inputs (``y10_chg_63d``, the inverted-curve verdict) are
read at the session itself and never combined with the VIX-dated inputs in one verdict.
Rolling windows count observations known by the session and are complete or
null (``WINDOW`` observations of the VIX for the percentile, so the statistics are null for the
first year of each series). No hysteresis: a verdict flips as its inputs do.

Licence (ADR 0088 decision A): the VIX-family values stay ``personal``; every ``_on`` verdict,
``short_premium_allowed`` and the calendar columns are our own aggregate and ``open``. A
reason names the condition ("the VIX curve is inverted"), never a value.

A verdict is null (UNKNOWN) when an input it needs is null; the Kleene helpers of
``indicators`` (``compare``, ``either``, ``both``) combine them. The thresholds are ``Params``
(``config/site/rollups.toml ["market_conditions@v2"]``); changing one is
``market_conditions@v3``.

v2 added ``realised_corr_ratio_21`` (design D6, ``dispersion``) to v1's columns; v1 was never
stored, so there is no v1 table to supersede.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import index_id, market_id
from algotrade.core.time.calendar import (
    is_last_session_of_week,
    session_weekday,
    sessions_ending,
    sessions_to,
)
from algotrade.core.time.windows import windows
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.corporate import earnings_expected
from algotrade.features.rollups.market import breadth, indicators, regime, trend
from algotrade.features.rollups.market.edges.dispersion import CLOSES, mean_member_vol
from algotrade.features.rollups.market.edges.labels import (
    LABELS,
    Bands,
    LabelReadings,
    classify,
    flags,
)
from algotrade.features.rollups.market.indicators import Verdict, both, compare, either
from algotrade.features.rollups.market.macro import MACRO
from algotrade.features.rollups.market.observations import Series, as_series, fresh

NAME = "market_conditions"
VERSION = 2
BARS = "bars/1d"
UNIVERSE = "universe"
REFERENCE = "instruments/reference"
TREASURY_10Y = "rates/treasury_10y"  # the 10-year par yield of each stored curve, by curve date
RELEASES = "events/macro_release"
MAX_AGE_SESSIONS = 3  # the newest VIX observation older than this is stale
WINDOW = 252  # observations of the percentile and median windows
HIGH_WINDOW = 20  # observations of the recent VIX high
CHANGE_OBS = 5  # observations of vix_chg_5d
YIELD_SESSIONS = 63  # sessions of y10_chg_63d
YIELD_TOLERANCE_DAYS = 5  # a curve this far before a target date stands in for it (holidays)
SEASON_SESSIONS = 10  # an expected report this many sessions ahead or less is "in season"
LOOKBACK = WINDOW + 20  # sessions of macro observations read
VIX, VIX3M, VIX9D, VIX6M, VVIX = (index_id(k) for k in ("VIX", "VIX3M", "VIX9D", "VIX6M", "VVIX"))
SERIES_IDS = (VIX, VIX3M, VIX9D, VIX6M, VVIX)
FOMC_KEY = "FOMC"


@dataclass(frozen=True)
class Params:
    """The verdict thresholds (research-options-regimes.md section 1, dimensions D1-D11)."""

    contango_below: float = 0.95  # D2: VIX / VIX3M below this is contango
    backwardation_at: float = 1.0  # D2: VIX / VIX3M at or above this is backwardation
    kink_at: float = 1.0  # D2: VIX9D / VIX at or above this is a front kink
    vrp_rich_at: float = 4.0  # D3: VIX minus realised vol, points, at or above: rich
    vrp_cheap_below: float = 0.0  # D3: ... below this: cheap
    vix_low_pct: float = 20.0  # D1: VIX percentile of its last 252 observations below: low
    vix_high_pct: float = 80.0  # D1: ... above: high
    recovery_off_high: float = 0.25  # D7: VIX at least this far below its 20-observation high
    rate_shock_at: float = (
        0.005  # D8: the 10-year yield up this much (decimal: 50 bp) in 63 sessions
    )
    vvix_high_above: float = 110.0  # D11: VVIX above this is high
    stress_at: float = 35.0  # R-A: VIX at or above this is the STRESS band (as ``vix_band``)
    corr_min_members: int = 50  # D6: complete stocks the mean member volatility needs
    # The label bands (``labels.Bands``; ``stress_at`` above is shared):
    calm_below: float = 25.0  # D1: VIX below this is CALM
    near_trend: float = -0.05  # D4: above the 200-day mean, or no further below it than this
    correction_lo: float = -0.15  # D4: a correction is a drawdown from this ...
    correction_hi: float = -0.05  # ... to this
    breadth_narrow: float = 0.50  # D5: fewer than this share above their 200-day mean
    breadth_bear: float = 0.30  # D5: fewer than this share in a bear trend
    corr_low: float = 0.30  # D6: the realised correlation ratio below this is dispersion
    backwardation_days: int = 10  # R6: inverted for this many closes; R7: fewer
    spike_chg: float = 0.40  # R7: VIX up this much over 5 observations
    thin_vrp: float = 2.0  # R2: VIX minus realised volatility below this is thin
    season_share: float = 0.15  # R9: this share of names about to report
    fomc_days: int = 5  # R10: an FOMC decision within this many sessions

    def __post_init__(self) -> None:
        if not 0 <= self.vix_low_pct < self.vix_high_pct <= 100:
            raise ValueError("need 0 <= vix_low_pct < vix_high_pct <= 100")
        if not 0 < self.recovery_off_high < 1:
            raise ValueError("recovery_off_high must be in (0, 1)")
        if self.corr_min_members < 1:
            raise ValueError("corr_min_members must be >= 1")
        if not self.correction_lo < self.correction_hi < 0:
            raise ValueError("need correction_lo < correction_hi < 0")

    def bands(self) -> Bands:
        """The label thresholds of these parameters."""
        return Bands(
            calm_below=self.calm_below, stress_at=self.stress_at, near_trend=self.near_trend,
            correction_lo=self.correction_lo, correction_hi=self.correction_hi,
            breadth_narrow=self.breadth_narrow, breadth_bear=self.breadth_bear,
            corr_low=self.corr_low, backwardation_days=self.backwardation_days,
            spike_chg=self.spike_chg, thin_vrp=self.thin_vrp, season_share=self.season_share,
            fomc_days=self.fomc_days,
        )  # fmt: skip


D = Params()
_UNKNOWN = (
    f"no VIX observation known by the session, or its newest is more than {MAX_AGE_SESSIONS} "
    "sessions old (stale: nothing is read)"
)
_SERIES = tuple(f"series:{k}" for k in ("VIX", "VIX3M", "VIX9D", "VIX6M", "VVIX"))
_RV = trend.GROUP.feature("spx_realised_vol_20d").key
_SMA = trend.GROUP.feature("spx_close_vs_sma200").key
_CURVE_ON = indicators.GROUP.feature("curve_10y3m_on").key
_OWN_VIX, _OWN_VIX3M, _OWN9D, _OWN_VVIX, _OWN_PCT = (  # the verdicts read the stored values
    f"{NAME}.{c}@v{VERSION}" for c in ("vix", "vix3m", "vix9d", "vvix", "vix_pct_252")
)
_OWN_HIGH, _OWN_MEDIAN, _OWN_CHG = (
    f"{NAME}.{c}@v{VERSION}" for c in ("vix_high_20", "vix_median_252", "vix_chg_5d")
)
_CROSS = trend.GROUP.feature("spx_sma50_vs_sma200").key
_DRAWDOWN = trend.GROUP.feature("spx_drawdown_252d").key
_BREADTH = breadth.GROUP.feature("pct_above_sma200").key
_CORR = f"{NAME}.realised_corr_ratio_21@v{VERSION}"
_CREDIT = indicators.GROUP.feature("hy_oas_on").key
_REGIME = regime.GROUP.feature("label").key
_YIELD = f"{TREASURY_10Y}.rate_par"
_FOMC = f"{RELEASES}.release_date"
_SEASON = earnings_expected.GROUP.feature("sessions_to_expected_report").key


def _personal(
    name: str, dtype: str, unit: str, description: str, null: str, inputs: tuple[str, ...],
    valid_range: tuple[float, float] | None = None,
) -> Feature:  # fmt: skip
    return Feature(name, dtype, unit, description, null, valid_range=valid_range, inputs=inputs,
                   licence="personal")  # fmt: skip


def _open(
    name: str, dtype: str, unit: str, description: str, null: str, inputs: tuple[str, ...],
    valid_range: tuple[float, float] | None = None,
) -> Feature:  # fmt: skip
    return Feature(name, dtype, unit, description, null, valid_range=valid_range, inputs=inputs)


_V1 = _SERIES[0]
FEATURES = (
    _personal(
        "vix",
        "float32",
        "pct_points",
        "Cboe VIX close on the shared observation date (20 = 20% implied vol)",
        _UNKNOWN,
        (_SERIES[0],),
        (0, 150),
    ),
    _personal(
        "vix3m",
        "float32",
        "pct_points",
        "Cboe 3-month VIX close on the shared observation date",
        f"{_UNKNOWN}; or VIX3M has no close on that date",
        (_SERIES[0], _SERIES[1]),
        (0, 150),
    ),
    _personal(
        "vix9d",
        "float32",
        "pct_points",
        "Cboe 9-day VIX close on the shared observation date (20 = 20% implied vol)",
        f"{_UNKNOWN}; or VIX9D has no close on that date (it starts in 2011)",
        (_SERIES[0], _SERIES[2]),
        (0, 150),
    ),
    _personal(
        "vix6m",
        "float32",
        "pct_points",
        "Cboe 6-month VIX close on the shared observation date",
        f"{_UNKNOWN}; or VIX6M has no close on that date (it starts in 2008)",
        (_SERIES[0], _SERIES[3]),
        (0, 150),
    ),
    _personal(
        "vvix",
        "float32",
        "pct_points",
        "Cboe VIX-of-VIX close on the shared observation date",
        f"{_UNKNOWN}; or VVIX has no close on that date (it starts in 2006)",
        (_SERIES[0], _SERIES[4]),
        (0, 400),
    ),
    _personal(
        "vix_obs_date",
        "date",
        "date",
        "The observation date of the VIX close the other "
        "VIX-family columns share (known from the session after it)",
        _UNKNOWN,
        (_V1,),
    ),
    _personal(
        "vix_pct_252",
        "float32",
        "pct_points",
        "Share of the last 252 VIX observations "
        "at or below the latest, in percent (0 is the lowest of a year, 100 the highest)",
        f"{_UNKNOWN}; or fewer than {WINDOW} observations are known",
        (_V1,),
        (0, 100),
    ),
    _personal(
        "vix_median_252",
        "float32",
        "pct_points",
        "Median of the last 252 VIX observations",
        f"{_UNKNOWN}; or fewer than {WINDOW} observations are known",
        (_V1,),
        (0, 150),
    ),
    _personal(
        "vix_high_20",
        "float32",
        "pct_points",
        "Highest of the last 20 VIX observations",
        f"{_UNKNOWN}; or fewer than {HIGH_WINDOW} observations are known",
        (_V1,),
        (0, 150),
    ),
    _personal(
        "vix_chg_5d",
        "float32",
        "decimal",
        "VIX over its value 5 observations earlier, minus 1 (0.25 is up 25%)",
        f"{_UNKNOWN}; or fewer than {CHANGE_OBS + 1} observations are known",
        (_V1,),
        (-1, 20),
    ),
    _personal(
        "backwardation_run",
        "int",
        "count",
        "Consecutive VIX observations up to the "
        "shared date with VIX / VIX3M at or above 1 (0: the curve is not inverted)",
        f"{_UNKNOWN}; or VIX3M has no close on the shared date",
        (_SERIES[0], _SERIES[1]),
        (0, 5000),
    ),
    _personal(
        "vvix_pct_252",
        "float32",
        "pct_points",
        "Share of the last 252 VVIX observations at or below the latest, in percent",
        f"{_UNKNOWN}; or VVIX has no close on the shared date or fewer than {WINDOW} observations",
        (_SERIES[0], _SERIES[4]),
        (0, 100),
    ),
    _open(
        "y10_chg_63d",
        "float32",
        "decimal",
        "The 10-year par Treasury yield minus its value "
        "63 sessions earlier (0.005 is up 50 basis points)",
        "the session or the date 63 sessions back has no stored curve within 5 days",
        (_YIELD,),
        (-0.1, 0.1),
    ),
    _open(
        "vix_contango_on",
        "bool",
        "flag",
        "The VIX curve slopes up: VIX is below 95% of VIX3M",
        _UNKNOWN + "; or VIX3M has no close on the shared date",
        (_OWN_VIX, _OWN_VIX3M),
    ),
    _open(
        "vix_front_kink_on",
        "bool",
        "flag",
        "Front-end stress: the 9-day VIX is at or above the 30-day VIX",
        _UNKNOWN + "; or VIX9D has no close on the shared date",
        (_OWN_VIX, _OWN9D),
    ),
    _open(
        "index_vrp_rich_on",
        "bool",
        "flag",
        "Index options price in at least 4 points more "
        "movement than the S&P 500 delivered (VIX minus 20-session realised volatility)",
        _UNKNOWN + f"; or {_RV} is null",
        (_OWN_VIX, _RV),
    ),
    _open(
        "index_vrp_cheap_on",
        "bool",
        "flag",
        "Index options price in less movement than the "
        "S&P 500 delivered (VIX below 20-session realised volatility)",
        _UNKNOWN + f"; or {_RV} is null",
        (_OWN_VIX, _RV),
    ),
    _open(
        "post_spike_recovery_on",
        "bool",
        "flag",
        "Volatility is falling back after a spike: "
        "VIX at least 25% below its 20-observation high, the curve back in contango and VIX "
        "still above its one-year median",
        _UNKNOWN + "; or a rolling window is incomplete",
        (_OWN_VIX, _OWN_VIX3M, _OWN_HIGH, _OWN_MEDIAN),
    ),
    _open(
        "rate_shock_on",
        "bool",
        "flag",
        "Interest rates are rising fast: the 10-year yield is "
        "up 50 basis points or more in 63 sessions, or the yield curve has been inverted for "
        "about a month",
        "the yield change or the curve verdict is unknown and the other is not on",
        (_YIELD, _CURVE_ON),
    ),
    _open(
        "vvix_high_on",
        "bool",
        "flag",
        "The market's volatility of volatility is high: VVIX above 110",
        f"{_UNKNOWN}; or VVIX has no close on the shared date",
        (_OWN_VVIX,),
    ),
    _open(
        "vix_low_on",
        "bool",
        "flag",
        "VIX is low for its year: below its 20th percentile of the last 252 observations",
        f"{_UNKNOWN}; or the year is incomplete",
        (_OWN_PCT,),
    ),
    _open(
        "vix_high_on",
        "bool",
        "flag",
        "VIX is high for its year: above its 80th percentile of the last 252 observations",
        f"{_UNKNOWN}; or the year is incomplete",
        (_OWN_PCT,),
    ),
    _open(
        "short_premium_allowed",
        "bool",
        "flag",
        "No stand-aside signal for option sellers: "
        "the VIX curve is not inverted, index options are not cheap against realised "
        "volatility outside a post-spike recovery, and the S&P 500 is not below its 200-day "
        "mean with VIX rising in the stress band",
        "a condition it needs is unknown and none of the others is on",
        (_OWN_VIX, _OWN_VIX3M, _OWN_HIGH, _OWN_MEDIAN, _OWN_CHG, _RV, _SMA),
    ),
    _open(
        "earnings_season_share",
        "float32",
        "decimal",
        "Share of the names with a known "
        "expected report date whose report is expected in the next 10 sessions (0.15 is "
        "peak season)",
        "no name has an expected report date for the session",
        (_SEASON,),
        (0, 1),
    ),
    _personal(
        "realised_corr_ratio_21",
        "float32",
        "ratio",
        "The S&P 500's realised volatility over the last 21 closes divided by the mean realised "
        "volatility of its member stocks over the same closes: near 1 when the names move "
        "together, low (0.3 or less) when they move apart (high dispersion)",
        "the S&P 500 realised volatility is unknown (or came from the index level, whose 20 "
        f"returns end a session before the stocks'), or fewer than {D.corr_min_members} "
        "members have a bar on each of the last 21 sessions, or no universe or reference "
        "snapshot is known before the session",
        (
            _RV,
            f"{BARS}.close",
            f"{UNIVERSE}.instrument_id",
            f"{UNIVERSE}.asset_class",
            f"{REFERENCE}.in_sp500",
        ),
        (0, 5),
    ),
    Feature(
        "conditions_label",
        "str",
        "category",
        "The market in one word, R1 to R12 by a fixed precedence (R6 bear, R7 spike in "
        "backwardation, R12 options cheap, R8 recovery, R5 rate shock, R4 correction, R3 narrow "
        "leadership, R2 low-vol grind, R1 calm uptrend, R11 macro high with the market calm) or "
        "UNCLASSIFIED when no rule holds; R9 and R10 are the flags earnings_season_on and "
        "event_week_on",
        "a rule of higher precedence than the first that holds is unknown (a label never skips "
        "an unknown rule), or every rule is unknown",
        kind="label",
        categories=LABELS,
        inputs=(
            _OWN_VIX,
            _OWN_VIX3M,
            _OWN_CHG,
            _OWN_PCT,
            _RV,
            _SMA,
            _CROSS,
            _DRAWDOWN,
            _BREADTH,
            _CORR,
            _CREDIT,
            _REGIME,
        ),
    ),
    _open(
        "earnings_season_on",
        "bool",
        "flag",
        "Earnings season: at least 15% of the names with an expected report date report within "
        "the next 10 sessions (R9: a flag over any regime)",
        "no name has an expected report date for the session",
        (_SEASON,),
    ),
    _open(
        "event_week_on",
        "bool",
        "flag",
        "Event week: an FOMC decision within 5 sessions, or an option expiry week (R10: a flag "
        "over any regime)",
        "no FOMC decision is known ahead and it is not an expiry week",
        (_FOMC,),
    ),
    _open(
        "sessions_to_fomc",
        "int",
        "sessions",
        "Sessions from the session to the next FOMC decision known by it (0: a decision today)",
        "no future FOMC decision is known by the session",
        (_FOMC,),
        (0, 400),
    ),
    _open(
        "fomc_cycle_week",
        "int",
        "count",
        "Whole 7-day periods since the latest FOMC decision on or "
        "before the session (0: the first 6 days)",
        "no FOMC decision is known before the session",
        (_FOMC,),
        (0, 60),
    ),
    _open(
        "in_opex_week",
        "bool",
        "flag",
        "The session is one of the 5 sessions ending on the month's option expiry",
        "never",
        (),
    ),
    _open(
        "weekday",
        "int",
        "count",
        "The session's weekday: 0 Monday to 4 Friday",
        "never",
        (),
        (0, 4),
    ),
    _open(
        "last_before_weekend",
        "bool",
        "flag",
        "The session is the last of its week (the next session falls in a later week)",
        "never",
        (),
    ),
)
COLUMNS = column_types(FEATURES)


def _none(value: Verdict) -> Verdict:
    """Kleene not."""
    return None if value is None else not value


def _at(s: Series | None, day: pd.Timestamp) -> float:
    """The value observed exactly on ``day`` (NaN: none: never an older one)."""
    if s is None or day not in s.index:
        return np.nan
    return float(s.loc[day])


def _window(s: Series | None, day: pd.Timestamp, n: int) -> np.ndarray | None:
    """The last ``n`` observations up to ``day`` (``None``: fewer are known)."""
    if s is None:
        return None
    known = s[s.index <= day]
    return known.to_numpy(float)[-n:] if len(known) >= n else None


def _rank(window: np.ndarray | None) -> float:
    """The share of ``window`` at or below its last value, in percent."""
    return np.nan if window is None else float((window <= window[-1]).mean() * 100.0)


def _run(vix: Series, vix3m: Series | None, day: pd.Timestamp, at: float) -> float:
    """Consecutive shared observations up to ``day`` with VIX / VIX3M at or above ``at``."""
    if vix3m is None or day not in vix3m.index:
        return np.nan
    both_ = pd.concat({"a": vix, "b": vix3m}, axis=1, join="inner").sort_index()
    ratio = (both_["a"] / both_["b"])[both_.index <= day].to_numpy(float)
    count = 0
    for r in ratio[::-1]:
        if not r >= at:
            break
        count += 1
    return float(count)


type Readings = dict[str, float]  # the VIX-family numbers of one session, NaN where unknown
_NUMBERS = (
    "vix", "vix3m", "vix9d", "vix6m", "vvix", "vix_pct_252", "vix_median_252", "vix_high_20",
    "vix_chg_5d", "backwardation_run", "vvix_pct_252",
)  # fmt: skip
STORED_NUMBERS = _NUMBERS


def vix_readings(
    series: dict[str, Series], session: date, p: Params
) -> tuple[Readings, date | None]:
    """The VIX-family numbers for ``session`` and the shared observation date (``None`` with
    every number NaN when the VIX is missing or stale)."""
    out = dict.fromkeys(_NUMBERS, np.nan)
    vix = series.get(VIX)
    if vix is None or not fresh(vix, session, MAX_AGE_SESSIONS):
        return out, None
    day = pd.Timestamp(vix.index[-1])
    now, vvix = float(vix.iloc[-1]), series.get(VVIX)
    year, recent, change = _window(vix, day, WINDOW), _window(vix, day, HIGH_WINDOW), None
    change = _window(vix, day, CHANGE_OBS + 1)
    out.update(
        vix=now,
        vix3m=_at(series.get(VIX3M), day),
        vix9d=_at(series.get(VIX9D), day),
        vix6m=_at(series.get(VIX6M), day),
        vvix=_at(vvix, day),
        vix_pct_252=_rank(year),
        vix_median_252=np.nan if year is None else float(np.median(year)),
        vix_high_20=np.nan if recent is None else float(recent.max()),
        vix_chg_5d=np.nan if change is None else now / float(change[0]) - 1.0,
        backwardation_run=_run(vix, series.get(VIX3M), day, p.backwardation_at),
    )  # fmt: skip
    if not np.isnan(out["vvix"]):
        out["vvix_pct_252"] = _rank(_window(vvix, day, WINDOW))
    return out, day.date()


def y10_change(frame: pd.DataFrame | None, session: date) -> float:
    """The 10-year par yield on or before ``session`` minus the one on or before the session
    ``YIELD_SESSIONS`` earlier (each within ``YIELD_TOLERANCE_DAYS``); NaN when either is
    missing."""
    if frame is None or frame.empty:
        return np.nan
    days = pd.to_datetime(frame["session_date"])
    rate = pd.Series(frame["rate_par"].to_numpy(float), index=pd.DatetimeIndex(days)).sort_index()

    def near(day: date) -> float:
        ts = pd.Timestamp(day)
        before = rate[rate.index <= ts]
        if before.empty or (ts - before.index[-1]).days > YIELD_TOLERANCE_DAYS:
            return np.nan
        return float(before.iloc[-1])

    return near(session) - near(sessions_ending(session, YIELD_SESSIONS + 1)[0])


def fomc_dates(releases: pd.DataFrame | None, session: date) -> list[date]:
    """The FOMC decision dates known by ``session`` (the latest version of each date known by
    it, a ``moved`` one dropped), ascending."""
    if releases is None or releases.empty:
        return []
    rows = releases[releases["release_key"] == FOMC_KEY]
    rows = rows[pd.to_datetime(rows["known_from"]).dt.date <= session]
    if rows.empty:
        return []
    rows = rows.sort_values(["known_from", "session_date"], kind="stable")
    latest = rows.drop_duplicates("release_date", keep="last")
    live = latest[latest["status"] != "moved"]
    return sorted(pd.to_datetime(live["release_date"]).dt.date.tolist())


def calendar_columns(releases: pd.DataFrame | None, session: date) -> dict[str, Any]:
    """The calendar columns: FOMC distances from the dates known by ``session``, the opex week
    and the weekday from the exchange calendar."""
    known = fomc_dates(releases, session)
    ahead = [d for d in known if d >= session]
    behind = [d for d in known if d <= session]
    opex = any(session in w for w in windows("opex_week", session - timedelta(10),
                                             session + timedelta(10)))  # fmt: skip
    return {
        "sessions_to_fomc": sessions_to(session, ahead[0]) if ahead else np.nan,
        "fomc_cycle_week": (session - behind[-1]).days // 7 if behind else np.nan,
        "in_opex_week": opex,
        "weekday": session_weekday(session),
        "last_before_weekend": is_last_session_of_week(session),
    }


def season_share(expected: pd.DataFrame | None) -> float:
    """Of the names with an expected report date, the share expecting one within
    ``SEASON_SESSIONS`` sessions (NaN: no name has a date)."""
    if expected is None or expected.empty:
        return np.nan
    ahead = pd.to_numeric(expected["sessions_to_expected_report"], errors="coerce").dropna()
    return float((ahead <= SEASON_SESSIONS).mean()) if len(ahead) else np.nan


def verdicts(v: Readings, y10: float, rv: float, sma: float,
             curve_on: Verdict, p: Params) -> dict[str, Verdict]:  # fmt: skip
    """Every ``_on`` verdict and ``short_premium_allowed`` from the session's readings."""
    vix, vix3m = v["vix"], v["vix3m"]
    ratio = vix / vix3m if vix3m else np.nan
    vrp = vix - rv * 100.0 if not np.isnan(rv) else np.nan
    high20 = v["vix_high_20"]
    off_high = vix / high20 if high20 else np.nan
    contango = compare(ratio, "<", p.contango_below)
    back = compare(ratio, ">=", p.backwardation_at)
    cheap = compare(vrp, "<", p.vrp_cheap_below)
    recovery = both(compare(off_high, "<=", 1.0 - p.recovery_off_high),
                    compare(ratio, "<", p.backwardation_at),
                    compare(vix - v["vix_median_252"], ">", 0.0))  # fmt: skip
    stress_fall = both(compare(sma, "<", 0.0), compare(v["vix_chg_5d"], ">", 0.0),
                       compare(vix, ">=", p.stress_at))  # fmt: skip
    stand_aside = either(back, both(cheap, _none(recovery)), stress_fall)
    return {
        "vix_contango_on": contango,
        "vix_front_kink_on": compare(v["vix9d"] / vix if vix else np.nan, ">=", p.kink_at),
        "index_vrp_rich_on": compare(vrp, ">=", p.vrp_rich_at),
        "index_vrp_cheap_on": cheap,
        "post_spike_recovery_on": recovery,
        "rate_shock_on": either(compare(y10, ">=", p.rate_shock_at), curve_on),
        "vvix_high_on": compare(v["vvix"], ">", p.vvix_high_above),
        "vix_low_on": compare(v["vix_pct_252"], "<", p.vix_low_pct),
        "vix_high_on": compare(v["vix_pct_252"], ">", p.vix_high_pct),
        "short_premium_allowed": _none(stand_aside),
    }


def _row_on(frame: pd.DataFrame | None, column: str, day: date | None) -> float:
    """``column`` of the row dated ``day`` (NaN: no such row, never another date's)."""
    if frame is None or frame.empty or day is None or "session_date" not in frame.columns:
        return np.nan
    rows = frame[pd.to_datetime(frame["session_date"]).dt.date == day]
    return _row(rows, column)


def _row(frame: pd.DataFrame | None, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return np.nan
    value = frame.iloc[-1][column]
    return float(value) if pd.notna(value) else np.nan


def compute(inputs: Inputs, session: date, params: Params) -> pd.DataFrame:
    series = as_series(inputs[MACRO])
    v, obs_date = vix_readings(series, session, params)
    trend_rows = inputs.get(trend.GROUP.table)
    ind_rows = inputs.get(indicators.GROUP.table)
    curve_on = _row(ind_rows, "curve_10y3m_on")
    y10 = y10_change(inputs.get(TREASURY_10Y), session)
    states = verdicts(v, y10, _row_on(trend_rows, "spx_realised_vol_20d", obs_date),
                      _row_on(trend_rows, "spx_close_vs_sma200", obs_date),
                      None if np.isnan(curve_on) else bool(curve_on), params)  # fmt: skip
    row: dict[str, object] = {"instrument_id": market_id("US")}
    row.update({k: v[k] for k in STORED_NUMBERS})
    row["vix_obs_date"] = obs_date
    row["y10_chg_63d"] = y10
    row.update(states)
    corr = corr_ratio(
        _index_vol_on_bars(trend_rows, session),
        mean_member_vol(
            inputs.get(UNIVERSE),
            inputs.get(REFERENCE),
            inputs.get(BARS),
            session,
            params.corr_min_members,
        ),
    )
    row["realised_corr_ratio_21"] = corr
    share = season_share(inputs.get(earnings_expected.GROUP.table))
    calendar = calendar_columns(inputs.get(RELEASES), session)
    row["earnings_season_share"] = share
    row.update(calendar)
    bands = params.bands()
    row["earnings_season_on"], row["event_week_on"] = flags(
        share,
        float(calendar["sessions_to_fomc"]),
        bool(calendar["in_opex_week"]),
        bands,
    )
    row["conditions_label"] = classify(
        label_readings(inputs, obs_date, v, trend_rows, ind_rows, states, corr), bands
    )
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


def _text_on(frame: pd.DataFrame | None, column: str, day: date | None) -> str | None:
    """``column`` of the row dated ``day`` as text (None: no such row or a null)."""
    if frame is None or frame.empty or day is None or column not in frame.columns:
        return None
    rows = frame[pd.to_datetime(frame["session_date"]).dt.date == day]
    value = rows.iloc[-1][column] if len(rows) else None
    return None if value is None or pd.isna(value) else str(value)


def label_readings(
    inputs: Inputs,
    obs_date: date | None,
    v: dict[str, float],
    trend_rows: pd.DataFrame | None,
    ind_rows: pd.DataFrame | None,
    states: dict[str, Verdict],
    corr: float,
) -> LabelReadings:
    """What the label rules read: the VIX-family numbers, the S&P 500 and breadth rows dated the
    VIX's date (never the session's own), the credit card and the headline regime label."""
    breadth_rows = inputs.get(breadth.GROUP.table)
    regime_rows = inputs.get(regime.GROUP.table)
    pct = _row_on(breadth_rows, "pct_above_sma200", obs_date)
    then = (
        _row_on(breadth_rows, "pct_above_sma200", sessions_ending(obs_date, 6)[0])
        if obs_date is not None
        else np.nan
    )
    rv = _row_on(trend_rows, "spx_realised_vol_20d", obs_date)
    macro = _text_on(regime_rows, "label", obs_date)
    credit = _row(ind_rows, "hy_oas_on")
    return LabelReadings(
        vix=v["vix"],
        ratio=v["vix"] / v["vix3m"] if v["vix3m"] else np.nan,
        run=v["backwardation_run"],
        chg_5d=v["vix_chg_5d"],
        pct_252=v["vix_pct_252"],
        vrp=v["vix"] - rv * 100.0 if not np.isnan(rv) else np.nan,
        drawdown=_row_on(trend_rows, "spx_drawdown_252d", obs_date),
        sma_200=_row_on(trend_rows, "spx_close_vs_sma200", obs_date),
        cross_50_200=_row_on(trend_rows, "spx_sma50_vs_sma200", obs_date),
        breadth=pct,
        breadth_falling=compare(pct - then, "<", 0.0),
        corr_ratio=corr,
        credit_on=None if np.isnan(credit) else bool(credit),
        macro_high=None if macro is None else macro == "CAUTION",
        cheap=states["index_vrp_cheap_on"],
        recovery=states["post_spike_recovery_on"],
        rate_shock=states["rate_shock_on"],
    )


def _index_vol_on_bars(trend_rows: pd.DataFrame | None, session: date) -> float:
    """The S&P 500's 20-session realised volatility of ``session``'s trend row when it was
    measured from SPY's bars (closes through ``session``, like the stocks'); NaN when it came
    from the index level, whose pit lag ends the window a session earlier."""
    if trend_rows is None or trend_rows.empty or "spx_source" not in trend_rows.columns:
        return np.nan
    day = pd.to_datetime(trend_rows["session_date"]).dt.date
    rows = trend_rows[(day == session) & (trend_rows["spx_source"] == "bars")]
    return _row(rows, "spx_realised_vol_20d")


def corr_ratio(index_vol: float, member_vol: float) -> float:
    """Index over mean member volatility (NaN when either is unknown or the members are flat)."""
    return index_vol / member_vol if member_vol > 0 else np.nan


_BREADTH_BACK = MAX_AGE_SESSIONS + 5  # the row of the VIX's date and the one 5 sessions before it


def _lookback(p: Params) -> int:
    return 0


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The market a setup enters: VIX-family statistics, the open verdicts of the volatility, "
    "term-structure, rate, event and earnings dimensions, the stand-aside verdict for option "
    "sellers and the calendar distances; a leaf nothing in the headline regime reads",
    (
        Input(MACRO, lookback=LOOKBACK, required=False, ids=SERIES_IDS),
        Input(trend.GROUP.table, lookback=MAX_AGE_SESSIONS, required=False),
        Input(indicators.GROUP.table, lookback=_lookback, required=False),
        Input(TREASURY_10Y, lookback=YIELD_SESSIONS + 5, required=False),
        Input(RELEASES, lookback=0, required=False),
        Input(earnings_expected.GROUP.table, lookback=_lookback, required=False),
        Input(BARS, lookback=CLOSES - 1, required=False),
        Input(UNIVERSE, required=False),
        Input(REFERENCE, required=False),
        Input(breadth.GROUP.table, lookback=_BREADTH_BACK, required=False),
        Input(regime.GROUP.table, lookback=MAX_AGE_SESSIONS, required=False),
    ),
    FEATURES,
    compute,
    params=D,
    entity="market",
)
