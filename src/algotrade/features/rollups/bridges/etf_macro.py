"""``etf_macro@v1``: macro, volatility-term, CAPE and rate-differential signals as per-fund
columns, one row per fund of ``etf_map`` found in the reference (EB E5 extension, ADR 0074).

Inputs: ``macro/series`` (point in time by vintage, ``macro.series.known_window``: each value is
the latest observation known by the session), ``volatility/vx_futures`` (rows with ``known_from
<= session``: a trade date's settle is known from the next session, so a restated settle is
never read early) and ``instruments/symbol_ids`` (the funds by ticker, ADR 0018). A fund's row
carries only the signals ``etf_map`` gives it; every other column is null (UNKNOWN).

    hy_oas, ig_oas, baa10y, t10y3m, t10y2y, vix   the level and its 50- and 200-observation mean
    dfii10, wti, usd_broad                        the level and its 200-observation mean
    vix9d, vix3m, vix6m, vvix                     the level
    vx_basis                                      first monthly VX future's settle / VIX - 1
    vx_roll                                       second / first monthly future - 1
    cape                                          the fund's country CAPE (one column, 26 countries)
    fx_carry                                      the currency's 3-month rate minus the US one

Spreads, yields and rates are decimals (FRED's percents / 100). A level is null when its latest
known observation is older than ``max_age_*_days`` (a series that stopped updating must not look
current); a mean needs ``min_window_share`` of its window's observations. ``vx_basis`` needs the
VX trade date to be the VIX observation date (else the two are not one close), and the futures
are the monthly expiries after the session only (weeklies and expired contracts excluded).
CAPE is revised in place, so its history is not as-known (``macro.toml``): a backfill reads the
latest estimate, a caveat the edge notes carry. The licence of a column is the strictest of the
series it reads (``PERSONAL`` mirrors ``macro.toml``; a fitness test checks it).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import index_id, macro_id
from algotrade.core.time.calendar import sessions_ending, third_friday
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.bridges.etf_map import (
    CAPE_ETFS,
    FX_ETFS,
    RATE_SERIES,
    SIGNAL_ETFS,
    carriers,
)
from algotrade.features.rollups.market.observations import HISTORY_SESSIONS, Series, as_series
from algotrade.features.rollups.market.tickers import SYMBOL_IDS, ticker_ids

NAME = "etf_macro"
VERSION = 1
MACRO = "macro/series"
VX = "volatility/vx_futures"
PERCENT = 100.0
MA_WINDOWS = (50, 200)
DAILY, DELAYED, MONTHLY = "daily", "delayed", "monthly"  # a series' staleness class


@dataclass(frozen=True)
class Params:
    """How old a level may be (calendar days from its observation to the session) and how
    complete a mean's window must be."""

    max_age_daily_days: int = 7  # a daily series (lag one day)
    max_age_delayed_days: int = 21  # a daily series published about ten days late (WTI, dollar)
    max_age_monthly_days: int = 100  # a monthly series (CAPE 45 days late, rates 60)
    min_window_share: float = 0.8  # of a mean's window that must have an observation

    def __post_init__(self) -> None:
        ages = (self.max_age_daily_days, self.max_age_delayed_days, self.max_age_monthly_days)
        if min(ages) < 1 or not 0 < self.min_window_share <= 1:
            raise ValueError(f"ages must be >= 1 and min_window_share in (0, 1], got {self}")


D = Params()


@dataclass(frozen=True)
class Use:
    """One registry series as read here: its id, divisor to a decimal and staleness class."""

    key: str
    cls: str = DAILY
    percent: bool = False
    index: bool = False

    @property
    def id(self) -> str:
        return index_id(self.key) if self.index else macro_id(self.key)

    @property
    def scale(self) -> float:
        return 1 / PERCENT if self.percent else 1.0


# column -> (series, the means it also stores, unit, valid range, what it is)
LEVELS: dict[str, tuple[Use, tuple[int, ...], str, tuple[float, float], str]] = {
    "hy_oas": (Use("BAMLH0A0HYM2", percent=True), MA_WINDOWS, "decimal", (0, 0.3),
               "ICE BofA US high-yield option-adjusted spread (0.05 = 5%)"),
    "ig_oas": (Use("BAMLC0A0CM", percent=True), MA_WINDOWS, "decimal", (0, 0.1),
               "ICE BofA US corporate (investment grade) option-adjusted spread"),
    "baa10y": (Use("BAA10Y", percent=True), MA_WINDOWS, "decimal", (0, 0.1),
               "Moody's Baa corporate yield minus the 10-year Treasury"),
    "t10y3m": (Use("T10Y3M", percent=True), MA_WINDOWS, "decimal", (-0.1, 0.1),
               "10-year minus 3-month Treasury yield (below 0: inverted)"),
    "t10y2y": (Use("T10Y2Y", percent=True), MA_WINDOWS, "decimal", (-0.1, 0.1),
               "10-year minus 2-year Treasury yield"),
    "vix": (Use("VIX", index=True), MA_WINDOWS, "pct_points", (0, 150),
            "Cboe VIX close (20 = 20% implied vol)"),
    "dfii10": (Use("DFII10", percent=True), (200,), "decimal", (-0.05, 0.1),
               "10-year TIPS real yield"),
    "wti": (Use("DCOILWTICO", DELAYED), (200,), "usd_per_share", (0, 300),
            "WTI crude spot, USD a barrel"),
    "usd_broad": (Use("DTWEXBGS", DELAYED), (200,), "index_points", (50, 200),
                  "Fed nominal broad US dollar index (Jan 2006 = 100)"),
    "vix9d": (Use("VIX9D", index=True), (), "pct_points", (0, 150), "Cboe 9-day VIX close"),
    "vix3m": (Use("VIX3M", index=True), (), "pct_points", (0, 150), "Cboe 3-month VIX close"),
    "vix6m": (Use("VIX6M", index=True), (), "pct_points", (0, 150), "Cboe 6-month VIX close"),
    "vvix": (Use("VVIX", index=True), (), "pct_points", (0, 400), "Cboe VIX-of-VIX close"),
}  # fmt: skip
VIX = LEVELS["vix"][0]
CAPES = {t: Use(key, MONTHLY) for t, key in CAPE_ETFS.items()}
RATES = {c: Use(key, MONTHLY, percent=True) for c, key in RATE_SERIES.items()}
USES = {
    u.id: u
    for u in (
        *(v[0] for v in LEVELS.values()), *CAPES.values(), *RATES.values(),
    )
}  # fmt: skip
# The registry's personal-use series (config/site/macro.toml licence; a fitness test checks it).
PERSONAL = frozenset(
    {"BAMLH0A0HYM2", "BAMLC0A0CM", "BAA10Y", "VIX", "VIX9D", "VIX3M", "VIX6M", "VVIX"}
    | set(CAPE_ETFS.values())
)


def _licence(keys: tuple[str, ...], vx: bool = False) -> Licence:
    return "personal" if vx or any(k in PERSONAL for k in keys) else "open"


def ma_name(column: str, n: int) -> str:
    return f"{column}_ma{n}"


def _none(what: str) -> str:
    return (
        f"{what} has no observation known by the session, or its latest is older than the "
        "series' maximum age (rollups.toml), or the fund does not carry this signal"
    )


def _features() -> tuple[Feature, ...]:
    out: list[Feature] = []
    for col, (use, mas, unit, rng, what) in LEVELS.items():
        inputs = (f"series:{use.key}",)
        lic = _licence((use.key,))
        out.append(Feature(col, "float32", unit, what, _none(use.key), valid_range=rng,
                           inputs=inputs, licence=lic))  # fmt: skip
        for n in mas:
            out.append(Feature(
                ma_name(col, n), "float32", unit, f"Mean of {col} over the last {n} sessions' "
                f"observations (needs {ceil(D.min_window_share * 100)}% of them)",
                f"{_none(use.key)}, or fewer than {ceil(D.min_window_share * n)} of the "
                f"{n} sessions have an observation", valid_range=rng, inputs=inputs,
                licence=lic,
            ))  # fmt: skip
    vx_in = (f"{VX}.settle", f"{VX}.expiry", "series:VIX")
    out += [
        Feature(
            "vx_basis",
            "float32",
            "decimal",
            "First monthly VIX future's settle over the VIX close, minus 1 (above 0: contango)",
            "no monthly future after the session "
            "has a settle, the futures' trade date is not the VIX observation date, or the "
            "curve is older than the daily maximum age",
            valid_range=(-1, 2),
            inputs=vx_in,
            licence="personal",
        ),
        Feature(
            "vx_roll",
            "float32",
            "decimal",
            "Second monthly VIX future's settle over the "
            "first, minus 1 (the one-month roll of the curve; above 0: contango)",
            "fewer than two monthly futures after the session have a settle, or the curve "
            "is older than the daily maximum age",
            valid_range=(-1, 2),
            inputs=(f"{VX}.settle", f"{VX}.expiry"),
            licence="personal",
        ),
        Feature(
            "cape",
            "float32",
            "ratio",
            "The fund's country cyclically adjusted P/E "
            "(Barclays' Shiller CAPE file: MSCI country index over 10-year real earnings); "
            "history is revised in place, so a backfill is not as-known",
            _none("the CAPE") + ", or the fund is not a country fund",
            valid_range=(0, 150),
            inputs=tuple(f"series:{u.key}" for u in CAPES.values()),
            licence="personal",
        ),
        Feature(
            "fx_carry",
            "float32",
            "decimal",
            "The currency's 3-month interbank rate minus "
            "the US one (0.02 = the currency yields 200 bp more), OECD via FRED",
            _none("the currency's or the US rate"),
            valid_range=(-0.2, 0.2),
            inputs=tuple(f"series:{u.key}" for u in RATES.values()),
            licence="open",
        ),
    ]
    return tuple(out)


FEATURES = _features()
COLUMNS = column_types(FEATURES)
SYMBOLS = f"{SYMBOL_IDS}.instrument_id"


def _max_age(use: Use, p: Params) -> int:
    return {
        DAILY: p.max_age_daily_days, DELAYED: p.max_age_delayed_days,
        MONTHLY: p.max_age_monthly_days,
    }[use.cls]  # fmt: skip


def known(series: dict[str, Series], use: Use, session: date, p: Params) -> Series | None:
    """The series' observations on or before the session, ``None`` when it has none or its
    latest is older than the class's maximum age."""
    s = series.get(use.id)
    if s is None:
        return None
    s = s[s.index <= pd.Timestamp(session)]
    if s.empty or (session - pd.Timestamp(s.index[-1]).date()).days > _max_age(use, p):
        return None
    return s


def level(series: dict[str, Series], use: Use, session: date, p: Params) -> float:
    s = known(series, use, session, p)
    return np.nan if s is None else float(s.iloc[-1]) * use.scale


def mean(series: dict[str, Series], use: Use, session: date, n: int, p: Params) -> float:
    """The mean of the observations dated in the last ``n`` sessions, when at least
    ``min_window_share`` of ``n`` are present."""
    s = known(series, use, session, p)
    if s is None:
        return np.nan
    window = s[s.index >= pd.Timestamp(sessions_ending(session, n)[0])]
    if len(window) < ceil(p.min_window_share * n):
        return np.nan
    return float(window.mean()) * use.scale


def is_monthly_expiry(expiry: date) -> bool:
    """Cboe's monthly VX expiry is the Wednesday 30 days before the next month's third Friday
    (the Tuesday, 31 days, when a holiday moves it); every other expiry is a weekly."""
    for days in (30, 31):
        d = expiry + timedelta(days=days)
        if third_friday(d.year, d.month) == d:
            return True
    return False


def vx_signals(
    vx: pd.DataFrame | None, series: dict[str, Series], session: date, p: Params
) -> tuple[float, float]:
    """(basis, roll) from the latest known trade date's monthly futures after the session."""
    nan = (np.nan, np.nan)
    if vx is None or vx.empty:
        return nan
    trade = vx["session_date"].max()
    if (session - trade).days > p.max_age_daily_days:
        return nan
    curve = vx[vx["session_date"] == trade]
    curve = curve[[e > session and is_monthly_expiry(e) for e in curve["expiry"]]]
    curve = curve.sort_values("expiry")
    if len(curve) < 1 or pd.isna(curve["settle"].iloc[0]) or curve["settle"].iloc[0] <= 0:
        return nan
    first = float(curve["settle"].iloc[0])
    roll = np.nan
    if len(curve) >= 2 and pd.notna(curve["settle"].iloc[1]) and curve["settle"].iloc[1] > 0:
        roll = float(curve["settle"].iloc[1]) / first - 1
    vix = known(series, VIX, session, p)
    same_day = vix is not None and pd.Timestamp(vix.index[-1]).date() == trade
    basis = first / float(vix.iloc[-1]) - 1 if same_day and vix is not None else np.nan
    return basis, roll


def signals(
    series: dict[str, Series], vx: pd.DataFrame | None, session: date, p: Params
) -> dict[str, float]:
    """Every national signal (the columns of ``LEVELS``, the means, ``vx_*``)."""
    out: dict[str, float] = {}
    for col, (use, mas, *_rest) in LEVELS.items():
        out[col] = level(series, use, session, p)
        for n in mas:
            out[ma_name(col, n)] = mean(series, use, session, n, p)
    out["vx_basis"], out["vx_roll"] = vx_signals(vx, series, session, p)
    return out


def carry(series: dict[str, Series], currency: str, session: date, p: Params) -> float:
    if currency not in RATES:  # no fresh series stored for it (EUR, GBP)
        return np.nan
    return level(series, RATES[currency], session, p) - level(series, RATES["USD"], session, p)


def compute(inputs: Inputs, session: date, params: Params) -> pd.DataFrame:
    ids = ticker_ids(inputs[SYMBOL_IDS], carriers())
    series = as_series(inputs[MACRO])
    national = signals(series, inputs[VX], session, params)
    rows = []
    for ticker, iid in sorted(ids.items()):
        row: dict[str, object] = dict.fromkeys(COLUMNS, np.nan)
        for col in national:
            base = col.split("_ma")[0]
            if ticker in SIGNAL_ETFS.get(base, ()):
                row[col] = national[col]
        if ticker in CAPES:
            row["cape"] = level(series, CAPES[ticker], session, params)
        if ticker in FX_ETFS:
            row["fx_carry"] = carry(series, FX_ETFS[ticker], session, params)
        rows.append({"instrument_id": iid, **row})
    return pd.DataFrame(rows, columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Macro signals as per-fund columns for allocation edges: credit spreads, the curve, real "
    "yield, oil, the dollar, the VIX term structure and VX futures, country CAPE and the "
    "FX carry, each carried by the fund that trades it",
    (
        Input(MACRO, lookback=HISTORY_SESSIONS, required=False, ids=tuple(USES)),
        Input(VX, lookback=5, required=False),
        Input(SYMBOL_IDS, required=False),
    ),
    FEATURES,
    compute,
    params=D,
)
