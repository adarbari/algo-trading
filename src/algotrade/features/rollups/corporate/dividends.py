"""``dividends@v2``: trailing-12-month cash dividends (ADR 0021).

Inputs: ``events/dividend`` and ``events/split`` by EVENT date (the ex-date / split date) up to
the session, and ``price_stats@v2`` for the session (``history_days``). One row per instrument
with a ``price_stats@v2`` row.

    div_ttm         sum of cash dividends with ex-date in (session - 365 days, session],
                    each in the session's share terms: divided by the ratio of every split
                    after its ex-date up to the session (a 4:1 split turns 0.82 into 0.205)
    div_count_ttm   how many ex-dates fell in the window
    last_ex_date    the latest ex-date in the window

An instrument with no dividend in the window is a non-payer (0) only when it has at least
``min_history_days`` bars among the last 252 sessions (``price_stats@v2.history_days``);
otherwise all three columns are null (UNKNOWN: too new, or bars do not cover the window). A
payer is a payer whatever its history (its sum covers every ex-date stored in the window).
Distributions typed ``special`` are left out unless ``include_special`` (a one-off is not a
yield). Event dates are what the source reports; the corporate-actions history must cover
the bars history for a zero to mean "pays nothing".

v2 (ADR 0023 step 3) stores ``div_ttm`` as a 32-bit float and drops ``div_yield``: the yield
(``div_ttm / close``, the continuous ``q`` in option pricing) is the expression feature
``div_yield`` (``config/site/features/fundamentals.toml``), materialised as
``rollups/instrument/div_yield@v1`` because ``iv30@v1`` reads it.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "dividends"
VERSION = 2
DIVIDENDS = "events/dividend"
SPLITS = "events/split"
PRICE_STATS = "rollups/instrument/price_stats@v2"
WINDOW_DAYS = 365
LOOKBACK = 260  # sessions of events loaded: more than 365 calendar days

_UNKNOWN = (
    "no dividend in the window and fewer than min_history_days (240) bars among the last 252 "
    "sessions (too new, or bars do not cover the window, to call it a non-payer)"
)
_DIVS = ("events/dividend.cash_amount", "events/dividend.ts", "events/split.ratio")

FEATURES = (
    Feature(
        "div_ttm", "float32", "usd_per_share",
        "Cash dividends with ex-date in the last 365 days, split-adjusted to the session's "
        "share terms (specials excluded); 0 for a known non-payer",
        _UNKNOWN, valid_range=(0, None), inputs=_DIVS,
    ),
    Feature(
        "div_count_ttm", "int", "count", "Ex-dates in the last 365 days",
        _UNKNOWN, valid_range=(0, None), inputs=("events/dividend.ts",),
    ),
    Feature(
        "last_ex_date", "date", "date", "The latest ex-date in the last 365 days",
        "no ex-date in the window (a non-payer, or unknown as for div_ttm)",
        inputs=("events/dividend.ts",),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class DividendParams:
    min_history_days: int = 240  # bars among the last 252 sessions for a zero to be known
    include_special: bool = False  # count distributions typed "special"

    def __post_init__(self) -> None:
        if not 1 <= self.min_history_days <= 252:
            raise ValueError("min_history_days must be between 1 and 252")


def split_factors(
    dividends: pd.DataFrame, splits: pd.DataFrame | None, session: date
) -> np.ndarray:
    """Per dividend row: the product of split ratios with ex-date in (dividend ex-date,
    session] for the same instrument (1 when none)."""
    factor = np.ones(len(dividends))
    if splits is None or splits.empty or dividends.empty:
        return factor
    later = splits[splits["event_date"] <= session]
    ids = dividends["instrument_id"].astype(str).to_numpy()
    days = dividends["event_date"].to_numpy()
    for iid, when, ratio in zip(
        later["instrument_id"].astype(str),
        later["event_date"],
        later["ratio"].astype(float),
        strict=True,
    ):
        factor[(ids == iid) & (days < when)] *= ratio
    return factor


def ttm(
    dividends: pd.DataFrame | None, splits: pd.DataFrame | None, session: date, p: DividendParams
) -> pd.DataFrame:
    """Per instrument with a dividend in the window: ``div_ttm``, ``div_count_ttm``,
    ``last_ex_date`` (split-adjusted to the session's share terms)."""
    columns = ["instrument_id", "div_ttm", "div_count_ttm", "last_ex_date"]
    if dividends is None or dividends.empty:
        return pd.DataFrame(columns=columns)
    start = session - timedelta(days=WINDOW_DAYS)
    rows = dividends[(dividends["event_date"] > start) & (dividends["event_date"] <= session)]
    if not p.include_special and "distribution_type" in rows.columns:
        rows = rows[rows["distribution_type"].astype(str) != "special"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    amount = rows["cash_amount"].to_numpy(dtype=float) / split_factors(rows, splits, session)
    grouped = rows.assign(amount=amount).groupby("instrument_id", sort=True)
    return pd.DataFrame(
        {
            "instrument_id": grouped.size().index.astype(str),
            "div_ttm": grouped["amount"].sum().to_numpy(),
            "div_count_ttm": grouped.size().to_numpy(),
            "last_ex_date": grouped["event_date"].max().to_numpy(),
        }
    )


def compute(inputs: Inputs, session: date, p: DividendParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session][["instrument_id", "history_days"]]
    paid = ttm(inputs.get(DIVIDENDS), inputs.get(SPLITS), session, p)
    out = today.merge(paid, on="instrument_id", how="left")
    known = out["history_days"].fillna(0).to_numpy() >= p.min_history_days
    payer = out["div_ttm"].notna().to_numpy()
    out["div_ttm"] = np.where(payer, out["div_ttm"], np.where(known, 0.0, np.nan))
    out["div_count_ttm"] = np.where(payer, out["div_count_ttm"], np.where(known, 0, np.nan))
    return out[["instrument_id", *COLUMNS]].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Trailing-12-month cash dividends, split-adjusted to the session",
    (
        Input(PRICE_STATS),
        Input(DIVIDENDS, lookback=LOOKBACK, required=False),
        Input(SPLITS, lookback=LOOKBACK, required=False),
    ),
    FEATURES,
    compute,
    DividendParams(),
)
