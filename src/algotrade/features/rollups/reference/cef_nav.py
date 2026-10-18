"""``cef_nav@v1``: how far a closed-end fund trades from its net asset value, now and against its
own year (the fields of the ``closed_end_fund_discounts`` and ``cef_distribution_trap`` edges, EB
E4).

Inputs: ``events/fund_nav`` (the daily NAV per share from Tiingo's Nasdaq MFQS series, edge build
D5; every row with ``known_from <= session``, the NAV known from the session after its date) and
``bars/1d`` (split-adjusted as of the session, the last 252 sessions). One row per fund with a NAV
dated within those 252 sessions; a fund that has no NAV stored has none.

A fund's NAV is struck after the close of its NAV date ``d``, so the premium or discount pairs the
NAV with the close of the SAME date ``d`` (never the session's close against a NAV a day old, which
would put a day's move into the "discount"):

    nav_per_share        the latest NAV known by the session (the unadjusted per-share value)
    nav_date             the date that NAV was struck (the session before the session for a fund
                         the vendor updates every day)
    cef_discount_to_nav  close on ``nav_date`` / ``nav_per_share`` - 1: negative is a discount
                         (-0.10: the shares cost 10% less than the assets behind them), positive a
                         premium
    cef_discount_zscore  the discount's distance from the fund's own year: its value minus the mean
                         of the discounts on the NAV dates of the last 252 sessions, over their
                         standard deviation (the Patro, Piccotti and Wu sort is on the discount
                         relative to its history)

The discount is null when the latest NAV is more than 5 sessions before the session (a stale NAV is
not a current discount), the close of its date is missing, or the NAV is not positive; the z-score
is null as well with fewer than 120 discounts in the window or no spread (UNKNOWN, never zero). A
NAV restated later replaces the original from the session that learned of it (D5): an earlier
session never sees it.

Caveats the maths does not remove: ``bars/1d`` is split-adjusted as of the session and the NAV is
not, so a fund that split or reverse-split inside the window shows a false discount until the NAV
history is read through the same adjustment (read ``valid_range`` as a sanity bound, not a filter);
and the NAV is the issuer's own, struck once a day, so a fund holding foreign or illiquid assets is
priced against a NAV stale at the close.
"""

from datetime import date

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_between, sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "cef_nav"
VERSION = 1
NAV = "events/fund_nav"
BARS = "bars/1d"
WINDOW = 252  # sessions the z-score reads, the session included
STALE_SESSIONS = 5  # a NAV older than this many sessions is no current discount
MIN_OBSERVATIONS = 120  # discounts the z-score needs
MIN_SPREAD = 1e-9  # a discount series flatter than this has no spread (float noise, not variation)
SERIES = "nav"

FEATURES = (
    Feature(
        "nav_per_share", "float32", "usd_per_share",
        "The latest net asset value per share known by the session, as the issuer struck it "
        "(not split-adjusted)",
        "no NAV is stored for the fund, or none dated within the last 252 sessions",
        valid_range=(0, None), licence="personal",
        inputs=(f"{NAV}.nav",),
    ),
    Feature(
        "nav_date", "date", "date",
        "The date that NAV was struck (known from the session after it)",
        "no NAV is stored for the fund, or none dated within the last 252 sessions",
        licence="personal",
        inputs=(f"{NAV}.ts",),
    ),
    Feature(
        "cef_discount_to_nav", "float32", "decimal",
        "The fund's close on the NAV's date over that NAV, minus 1: negative is a discount "
        "(-0.10: the shares cost 10% less than the assets), positive a premium",
        "the latest NAV is more than 5 sessions before the session, the fund has no bar on its "
        "date, or the NAV is not positive",
        valid_range=(-0.95, 5), licence="personal",
        inputs=(f"{NAV}.nav", f"{NAV}.ts", f"{BARS}.close"),
    ),
    Feature(
        "cef_discount_zscore", "float32", "ratio",
        "The discount minus its mean over the NAV dates of the last 252 sessions, over their "
        "standard deviation: negative is a wider discount than the fund's own year",
        "cef_discount_to_nav is null, fewer than 120 discounts are in the window, or they are "
        "all equal",
        valid_range=(-10, 10), licence="personal",
        inputs=(f"{NAV}.nav", f"{NAV}.ts", f"{BARS}.close"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _latest_navs(frame: pd.DataFrame, first: date) -> pd.DataFrame:
    """The NAV rows dated on or after ``first``, one per (fund, NAV date): the version known
    last (a restated NAV replaces the original), with ``day`` the NAV's date."""
    rows = frame[frame["series"].eq(SERIES)] if "series" in frame.columns else frame
    day = pd.to_datetime(rows["ts"], utc=True).dt.date
    rows = rows.assign(day=day)
    rows = rows[rows["day"] >= first]
    order = ["instrument_id", "day", "known_from", "session_date"]
    rows = rows.sort_values(order, kind="stable")
    rows = rows.drop_duplicates(["instrument_id", "day"], keep="last")
    return rows[["instrument_id", "day", "nav"]].reset_index(drop=True)


def _discounts(navs: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Each NAV paired with the close of its own date: ``discount`` (NaN: no bar that day or the
    NAV is not positive)."""
    closes = bars[["instrument_id", "session_date", "close"]].copy()
    closes["day"] = pd.to_datetime(closes["session_date"]).dt.date
    merged = navs.merge(closes[["instrument_id", "day", "close"]], how="left",
                        on=["instrument_id", "day"])  # fmt: skip
    nav = merged["nav"].astype(float).where(merged["nav"] > 0)
    merged["discount"] = merged["close"].astype(float) / nav - 1.0
    return merged


def _sessions_ago(day: date, session: date) -> int:
    return len(sessions_between(day, session)) - 1


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    first = sessions_ending(session, WINDOW)[0]
    columns = ["instrument_id", *COLUMNS]
    stored = inputs[NAV]
    navs = _latest_navs(stored, first) if stored is not None else None
    if navs is None or navs.empty:
        return pd.DataFrame({c: [] for c in columns})
    bars = inputs.get(BARS)
    paired = _discounts(navs, bars) if bars is not None else navs.assign(discount=np.nan)
    paired = paired.sort_values(["instrument_id", "day"], kind="stable")
    rows = []
    for fund, group in paired.groupby("instrument_id", sort=True):
        last = group.iloc[-1]
        discount = float(last["discount"])
        stale = _sessions_ago(last["day"], session) > STALE_SESSIONS
        current = np.nan if stale or not np.isfinite(discount) else discount
        seen = group["discount"].to_numpy(dtype=float)
        seen = seen[np.isfinite(seen)]
        z = np.nan
        if np.isfinite(current) and len(seen) >= MIN_OBSERVATIONS:
            spread = float(np.std(seen, ddof=1))
            z = (current - float(np.mean(seen))) / spread if spread > MIN_SPREAD else np.nan
        rows.append(
            {
                "instrument_id": str(fund),
                "nav_per_share": float(last["nav"]),
                "nav_date": last["day"],
                "cef_discount_to_nav": current,
                "cef_discount_zscore": z,
            }
        )
    return pd.DataFrame(rows, columns=columns)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How far a closed-end fund trades from its net asset value, and against its own year",
    (
        Input(NAV),
        Input(BARS, lookback=WINDOW - 1, required=False),
    ),
    FEATURES,
    compute,
)
