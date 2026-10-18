"""``etf_flows@v1``: how much an iShares fund's share count changed over about a month, the
creations and redemptions behind it (the field of the ``etf_flow_pressure`` edge, EB E4).

Input: ``holdings/etf_shares`` (the issuer's daily shares-outstanding count per fund, edge build
D4; every version of every row with ``known_from <= session``, a restated count seen from the
session that fetched it). One row per fund with a count dated within the last 30 calendar days. The
count comes from iShares' own files, so SPDR, Vanguard and every other issuer's funds have none,
and the stored history starts with D4's first nightly run (about 2026-10-17): a fund has a change
only once a count from a month earlier is stored.

    etf_shares_outstanding  the latest count known by the session
    etf_shares_asof         the issuer's date of that count
    etf_shares_chg_21d      the latest count over the count 21 sessions before the session, minus
                            1: positive is net creation (money in), negative net redemption

The count 21 sessions back is the latest count dated on or before that session and no more than 7
calendar days earlier (a fund the issuer lists weekly has a count a few days stale), and the latest
count must itself be dated within 7 days of the session. Otherwise the change is null (UNKNOWN,
never zero). Flows in dollars are not stored: a change in shares times a price approximates them,
and this field is the share change itself, which needs no price.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "etf_flows"
VERSION = 1
SHARES = "holdings/etf_shares"
HORIZON_SESSIONS = 21  # the change's span
FRESH_DAYS = 7  # the latest count's age, and how far a count may sit before the span's start
LISTED_DAYS = 30  # a fund whose latest count is older has no row

FEATURES = (
    Feature(
        "etf_shares_outstanding", "float", "count",
        "The issuer's latest shares outstanding for the fund known by the session (iShares files "
        "only)",
        "the fund has no count dated within the last 30 days: not an iShares fund, or not listed "
        "in the issuer's file",
        valid_range=(0, None),
        inputs=(f"{SHARES}.shares_outstanding",),
    ),
    Feature(
        "etf_shares_asof", "date", "date",
        "The issuer's date of that count",
        "the fund has no count dated within the last 30 days",
        inputs=(f"{SHARES}.as_of",),
    ),
    Feature(
        "etf_shares_chg_21d", "float32", "decimal",
        "The latest count over the count 21 sessions earlier, minus 1: positive is net creation, "
        "negative net redemption",
        "the latest count is more than 7 days old, or no count dated within the 7 days up to the "
        "session 21 sessions back is stored (the history starts about 2026-10-17)",
        valid_range=(-1, 20),
        inputs=(f"{SHARES}.shares_outstanding", f"{SHARES}.as_of"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _latest_versions(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per (fund, issuer date): the version known last (a restated count replaces it)."""
    order = ["instrument_id", "as_of", "known_from"]
    if "knowledge_ts" in frame.columns:
        order.append("knowledge_ts")
    rows = frame.sort_values(order, kind="stable")
    return rows.drop_duplicates(["instrument_id", "as_of"], keep="last")


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    frame = inputs[SHARES]
    columns = ["instrument_id", *COLUMNS]
    if frame is None or frame.empty:
        return pd.DataFrame({c: [] for c in columns})
    counts = _latest_versions(frame)
    counts = counts[counts["shares_outstanding"].astype(float) > 0]
    start = sessions_ending(session, HORIZON_SESSIONS + 1)[0]
    rows = []
    for fund, group in counts.sort_values(["instrument_id", "as_of"]).groupby("instrument_id"):
        last = group.iloc[-1]
        if (session - last["as_of"]).days > LISTED_DAYS:
            continue
        latest = float(last["shares_outstanding"])
        change = np.nan
        if (session - last["as_of"]).days <= FRESH_DAYS:
            base = group[
                (group["as_of"] <= start) & (group["as_of"] >= start - timedelta(days=FRESH_DAYS))
            ]
            if not base.empty:
                change = latest / float(base.iloc[-1]["shares_outstanding"]) - 1.0
        rows.append(
            {
                "instrument_id": str(fund),
                "etf_shares_outstanding": latest,
                "etf_shares_asof": last["as_of"],
                "etf_shares_chg_21d": change,
            }
        )
    return pd.DataFrame(rows, columns=columns)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How much an iShares fund's share count changed over about a month (creations less "
    "redemptions)",
    (Input(SHARES),),
    FEATURES,
    compute,
)
