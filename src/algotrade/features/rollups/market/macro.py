"""``market_macro@v1``: the slow macro readings of the regime model, one ``MKT:US`` row per
session (ADR 0047, ADR 0048; docs/market-regime-plan.md sections 3A and 3E).

Inputs: ``macro/series`` (the series of ``SERIES``, by id, point in time by vintage: each value
is the latest observation known by the session, however old: the ``macro`` task's staleness
check guards freshness) and ``rates/treasury`` (the session's own Treasury curve). The
registry's ``transform`` (``config/site/macro.toml``) is applied here, not at ingestion: ``yoy``
is the latest observation over the one a year earlier - 1, ``diff`` the latest minus the one a
year earlier. Rates, spreads and changes are decimals (FRED's percents / 100: a 5% spread is
0.05, 150 bp is 0.015).

    curve_10y3m, curve_10y2y  10y - 3m (2y) par yield from the session's own Treasury curve
                              when it has all three tenors, else FRED T10Y3M / T10Y2Y
                              (``curve_source`` says which)
    curve_inverted_days_252d  T10Y3M observations below zero among those of the last 252
                              sessions
    sahm_gap                  3-month mean unemployment minus its lowest 3-month mean of the
                              previous 12 months (the Sahm rule, from UNRATE's vintages)

Every column is null (UNKNOWN) when a series it reads has no observation known by the session
(no FRED key, or before the series starts) or its window is not complete; with no macro data at
all the row is still written, with every macro column null.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from algotrade.core.model.instruments import index_id, macro_id, market_id
from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, Licence
from algotrade.features.rollups.market.observations import (
    Series,
    change_12m,
    known_series,
    last_months,
    latest,
    since,
)

NAME = "market_macro"
VERSION = 1
MACRO = "macro/series"
TREASURY = "rates/treasury"
type Transform = Literal["level", "yoy", "diff"]


@dataclass(frozen=True)
class SeriesUse:
    """How the group reads one registry series: its ``transform`` (the registry's, checked by
    a test) and whether it is an index level (``IDX:``) rather than a macro series."""

    transform: Transform = "level"
    index: bool = False

    def id(self, key: str) -> str:
        return index_id(key) if self.index else macro_id(key)


SERIES: dict[str, SeriesUse] = {
    "T10Y3M": SeriesUse(),
    "T10Y2Y": SeriesUse(),
    "BAMLH0A0HYM2": SeriesUse(),
    "BAMLC0A0CM": SeriesUse(),
    "UNRATE": SeriesUse(),
    "IC4WSA": SeriesUse(),
    "PAYEMS": SeriesUse("yoy"),
    "PERMIT": SeriesUse("yoy"),
    "NFCI": SeriesUse(),
    "ANFCI": SeriesUse(),
    "DRTSCILM": SeriesUse(),
    "FEDFUNDS": SeriesUse("diff"),
    "DFII10": SeriesUse(),
    "CPIAUCSL": SeriesUse("yoy"),
    "PCEPILFE": SeriesUse("yoy"),
    "DCOILWTICO": SeriesUse("yoy"),
    "CFNAIMA3": SeriesUse(),
    "RECPROUSM156N": SeriesUse(),
    "GDPNOW": SeriesUse(),
    "TOTBKCR": SeriesUse("yoy"),
    "VIX": SeriesUse(index=True),
    "VIX3M": SeriesUse(index=True),
}
ID = {key: use.id(key) for key, use in SERIES.items()}
PERCENT = 100.0  # FRED quotes rates, spreads and probabilities in percent
CREDIT_SESSIONS = 126  # the HY spread's change and 6-month low
CURVE_SESSIONS = 252  # the inversion count
CLAIMS_DAYS = 364  # the 52-week low of the 4-week average of claims
TENORS = {"curve_10y3m": ("10Y", "3M", "T10Y3M"), "curve_10y2y": ("10Y", "2Y", "T10Y2Y")}
SOURCES = ("treasury", "fred")


def _none(*keys: str) -> str:
    named = ", ".join(keys)
    return f"no observation of {named} known by the session (no FRED key, or before it starts)"


def _f(
    name: str,
    unit: str,
    description: str,
    keys: tuple[str, ...],
    null: str = "",
    extra: tuple[str, ...] = (),
    valid_range: tuple[float, float] | None = None,
) -> Feature:
    """One float column over ``keys`` (personal when one of them is: ADR 0028)."""
    licence: Licence = "personal" if any(k in PERSONAL for k in keys) else "open"
    inputs = (*extra, *(f"series:{k}" for k in keys))
    return Feature(
        name, "float32", unit, description, null or _none(*keys),
        valid_range=valid_range, inputs=inputs, licence=licence,
    )  # fmt: skip


# The registry's personal-use series (config/site/macro.toml licence; a fitness test checks it).
PERSONAL = frozenset({"BAMLH0A0HYM2", "BAMLC0A0CM", "VIX", "VIX3M"})
_CURVE = (f"{TREASURY}.tenor", f"{TREASURY}.rate_par")
_YEAR = "a year before its latest observation"

FEATURES = (
    _f("curve_10y3m", "decimal", "10-year minus 3-month Treasury yield (below 0: inverted): the "
       "session's own par curve, else FRED T10Y3M", ("T10Y3M",),
       "the session has no Treasury curve with 10Y and 3M, and T10Y3M has no observation",
       extra=_CURVE, valid_range=(-0.1, 0.1)),
    _f("curve_10y2y", "decimal", "10-year minus 2-year Treasury yield: the session's own par "
       "curve, else FRED T10Y2Y", ("T10Y2Y",),
       "the session has no Treasury curve with 10Y and 2Y, and T10Y2Y has no observation",
       extra=_CURVE, valid_range=(-0.1, 0.1)),
    Feature("curve_source", "str", "category", "Where the curve columns come from: treasury "
            "(the session's stored par curve) or fred (T10Y3M / T10Y2Y)",
            "neither the session's curve nor the FRED series has a value", kind="label",
            categories=SOURCES, inputs=(*_CURVE, "series:T10Y3M", "series:T10Y2Y")),
    Feature("curve_inverted_days_252d", "int", "count", f"T10Y3M observations below zero among "
            f"those of the last {CURVE_SESSIONS} sessions (inverted days in the last year)",
            f"T10Y3M's known history does not reach back {CURVE_SESSIONS} sessions",
            valid_range=(0, 260), inputs=("series:T10Y3M",)),
    _f("hy_oas", "decimal", "ICE BofA US high-yield option-adjusted spread (0.05 = 5%)",
       ("BAMLH0A0HYM2",), valid_range=(0, 0.3)),
    _f("hy_oas_chg_126d", "decimal", f"High-yield spread now minus {CREDIT_SESSIONS} sessions "
       "earlier (0.015 = +150 bp)", ("BAMLH0A0HYM2",),
       f"no high-yield spread observation, or none within a week before {CREDIT_SESSIONS} "
       "sessions ago", valid_range=(-0.2, 0.2)),
    _f("hy_oas_vs_126d_low", "decimal", f"High-yield spread now minus its lowest of the last "
       f"{CREDIT_SESSIONS} sessions (0.015 = 150 bp off the 6-month low)", ("BAMLH0A0HYM2",),
       f"no high-yield spread observation, or its history does not reach back {CREDIT_SESSIONS} "
       "sessions", valid_range=(0, 0.2)),
    _f("ig_oas", "decimal", "ICE BofA US corporate (investment grade) option-adjusted spread",
       ("BAMLC0A0CM",), valid_range=(0, 0.1)),
    _f("unrate", "decimal", "Unemployment rate (0.041 = 4.1%)", ("UNRATE",),
       valid_range=(0, 0.3)),
    _f("unrate_vs_12m_avg", "decimal", "Unemployment rate minus its mean over the last 12 "
       "months (above 0: rising, the unemployment trend signal)", ("UNRATE",),
       "fewer than 12 consecutive monthly UNRATE observations known", valid_range=(-0.2, 0.2)),
    _f("sahm_gap", "decimal", "Sahm rule gap: 3-month mean unemployment minus the lowest "
       "3-month mean of the previous 12 months (0.005 = the rule's 0.5 point trigger)",
       ("UNRATE",), "fewer than 15 consecutive monthly UNRATE observations known",
       valid_range=(-0.05, 0.2)),
    _f("claims_4w_vs_52w_low", "ratio", "4-week average of initial jobless claims / its "
       "lowest of the last 52 weeks (1.15: 15% above the low)", ("IC4WSA",),
       "no IC4WSA observation, or its history does not reach back 52 weeks",
       valid_range=(1, 10)),
    _f("payrolls_yoy", "decimal", f"Nonfarm payrolls / {_YEAR} - 1", ("PAYEMS",),
       valid_range=(-0.2, 0.2)),
    _f("permits_yoy", "decimal", f"Housing permits / {_YEAR} - 1", ("PERMIT",),
       valid_range=(-1, 2)),
    _f("nfci", "ratio", "Chicago Fed National Financial Conditions Index (0 = average; above "
       "0: tighter than average)", ("NFCI",), valid_range=(-3, 10)),
    _f("anfci", "ratio", "Adjusted NFCI: financial conditions net of the economy's state",
       ("ANFCI",), valid_range=(-3, 10)),
    _f("sloos_ci_tightening", "decimal", "Senior loan officer survey: net share of banks "
       "tightening C&I lending standards (0.2 = 20%)", ("DRTSCILM",), valid_range=(-1, 1)),
    _f("fedfunds_chg_12m", "decimal", f"Effective fed funds rate minus {_YEAR} (0.02 = "
       "+200 bp)", ("FEDFUNDS",), valid_range=(-0.1, 0.1)),
    _f("real_10y", "decimal", "10-year TIPS real yield", ("DFII10",), valid_range=(-0.05, 0.1)),
    _f("cpi_yoy", "decimal", f"CPI (all items) / {_YEAR} - 1", ("CPIAUCSL",),
       valid_range=(-0.1, 0.3)),
    _f("core_pce_yoy", "decimal", f"Core PCE price index / {_YEAR} - 1", ("PCEPILFE",),
       valid_range=(-0.1, 0.3)),
    _f("wti_chg_12m", "decimal", f"WTI crude spot / {_YEAR} - 1 (above 0.5: an oil shock)",
       ("DCOILWTICO",), valid_range=(-1, 5)),
    _f("cfnai_ma3", "ratio", "Chicago Fed National Activity Index, 3-month mean (below -0.7: "
       "recession)", ("CFNAIMA3",), valid_range=(-30, 10)),
    _f("recession_prob_smoothed", "decimal", "Chauvet-Piger smoothed recession probability "
       "(0.3 = 30%)", ("RECPROUSM156N",), valid_range=(0, 1)),
    _f("gdpnow", "decimal", "Atlanta Fed GDPNow estimate of real GDP growth (annualised)",
       ("GDPNOW",), valid_range=(-0.6, 0.6)),
    _f("bank_credit_yoy", "decimal", f"Bank credit / {_YEAR} - 1 (credit expansion, Baron "
       "and Xiong)", ("TOTBKCR",), valid_range=(-0.5, 0.5)),
    _f("vix", "pct_points", "Cboe VIX close (20 = 20% implied vol)", ("VIX",),
       valid_range=(0, 150)),
    _f("vix3m", "pct_points", "Cboe 3-month VIX close", ("VIX3M",), valid_range=(0, 150)),
    _f("vix_term_ratio", "ratio", "VIX / VIX3M (above 1: backwardation, short-term stress)",
       ("VIX", "VIX3M"), valid_range=(0, 5)),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def curve_spreads(curve: pd.DataFrame | None, session: date) -> dict[str, float] | None:
    """10y - 3m and 10y - 2y par yields from the session's own curve (``None``: the session has
    no curve of its own, or it lacks a tenor)."""
    if curve is None or curve.empty or bool(curve["pre_snapshot"].iloc[0]):
        return None
    if pd.Timestamp(curve["curve_date"].iloc[0]).date() != session:
        return None
    rates = dict(zip(curve["tenor"].astype(str), curve["rate_par"].astype(float), strict=True))
    if not {"10Y", "3M", "2Y"} <= rates.keys():
        return None
    return {col: rates[long] - rates[short] for col, (long, short, _) in TENORS.items()}


def _inverted_days(s: Series | None, session: date) -> float:
    window = since(s, sessions_ending(session, CURVE_SESSIONS + 1)[0])
    return np.nan if window is None else float((window < 0).sum())


def _credit(s: Series | None, session: date) -> tuple[float, float]:
    """(change over ``CREDIT_SESSIONS``, distance above the low of that window)."""
    start = sessions_ending(session, CREDIT_SESSIONS + 1)[0]
    window = since(s, start)
    if s is None or window is None:
        return np.nan, np.nan
    then = float(s[s.index <= pd.Timestamp(start)].iloc[-1])
    low = min(float(window.min()), then)
    now = float(s.iloc[-1])
    return now - then, now - low


def _unemployment(s: Series | None) -> tuple[float, float]:
    """(latest minus the 12-month mean, the Sahm gap), in percent points."""
    year = last_months(s, 12)
    trend = np.nan if year is None else float(year.iloc[-1] - year.mean())
    months = last_months(s, 15)
    if months is None:
        return trend, np.nan
    ma3 = months.rolling(3).mean().to_numpy()
    return trend, float(ma3[-1] - np.min(ma3[2:-1]))


def _claims(s: Series | None) -> float:
    if s is None or s.empty:
        return np.nan
    window = since(s, (s.index[-1] - pd.Timedelta(days=CLAIMS_DAYS)).date())
    low = np.nan if window is None else float(window.min())
    return float(s.iloc[-1]) / low if low and not np.isnan(low) else np.nan


def _levels(series: Mapping[str, Series]) -> dict[str, float]:
    def pct(key: str) -> float:
        return latest(series, ID[key]) / PERCENT

    vix, vix3m = latest(series, ID["VIX"]), latest(series, ID["VIX3M"])
    return {
        "hy_oas": pct("BAMLH0A0HYM2"),
        "ig_oas": pct("BAMLC0A0CM"),
        "unrate": pct("UNRATE"),
        "nfci": latest(series, ID["NFCI"]),
        "anfci": latest(series, ID["ANFCI"]),
        "sloos_ci_tightening": pct("DRTSCILM"),
        "real_10y": pct("DFII10"),
        "cfnai_ma3": latest(series, ID["CFNAIMA3"]),
        "recession_prob_smoothed": pct("RECPROUSM156N"),
        "gdpnow": pct("GDPNOW"),
        "vix": vix,
        "vix3m": vix3m,
        "vix_term_ratio": vix / vix3m if vix3m else np.nan,
    }


def _changes(series: Mapping[str, Series]) -> dict[str, float]:
    def yoy(key: str) -> float:
        return change_12m(series, ID[key], ratio=SERIES[key].transform == "yoy")

    return {
        "payrolls_yoy": yoy("PAYEMS"),
        "permits_yoy": yoy("PERMIT"),
        "fedfunds_chg_12m": yoy("FEDFUNDS") / PERCENT,
        "cpi_yoy": yoy("CPIAUCSL"),
        "core_pce_yoy": yoy("PCEPILFE"),
        "wti_chg_12m": yoy("DCOILWTICO"),
        "bank_credit_yoy": yoy("TOTBKCR"),
    }


def macro_row(
    series: Mapping[str, Series], curve: pd.DataFrame | None, session: date
) -> dict[str, object]:
    """Every column for the session from the known ``series`` (by id) and the curve rows."""
    row: dict[str, object] = {**_levels(series), **_changes(series)}
    own = curve_spreads(curve, session)
    fred = {col: latest(series, ID[key]) / PERCENT for col, (_, _, key) in TENORS.items()}
    row.update(own or fred)
    known = own is not None or not all(np.isnan(v) for v in fred.values())
    row["curve_source"] = ("treasury" if own is not None else "fred") if known else None
    row["curve_inverted_days_252d"] = _inverted_days(series.get(ID["T10Y3M"]), session)
    hy = series.get(ID["BAMLH0A0HYM2"])
    chg, off_low = _credit(None if hy is None else hy / PERCENT, session)
    row["hy_oas_chg_126d"], row["hy_oas_vs_126d_low"] = chg, off_low
    unrate = series.get(ID["UNRATE"])
    trend, sahm = _unemployment(None if unrate is None else unrate / PERCENT)
    row["unrate_vs_12m_avg"], row["sahm_gap"] = trend, sahm
    row["claims_4w_vs_52w_low"] = _claims(series.get(ID["IC4WSA"]))
    return row


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    series = known_series(inputs[MACRO], session)
    row = {"instrument_id": market_id("US"), **macro_row(series, inputs[TREASURY], session)}
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Slow macro readings of the regime model: the yield curve, credit spreads, labour, "
    "financial conditions, lending, policy, inflation, activity and the VIX term structure, "
    "each the latest observation known by the session",
    (
        Input(MACRO, required=False, ids=tuple(ID.values())),
        Input(TREASURY, required=False),
    ),
    FEATURES,
    compute,
    entity="market",
)
