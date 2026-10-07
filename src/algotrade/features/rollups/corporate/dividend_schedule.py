"""``dividend_schedule@v1``: the next known ex-dividend date, as known on the session.

Inputs: ``events/dividend_declared`` (``events/dividend`` by KNOWLEDGE date: every dividend
row stored in a partition on or before the session, as stored; the table the other
dividend groups read by EVENT date up to the session, which never shows a declared future
ex-date), ``events/split`` by event date, and ``price_stats@v2`` for the session. One row per
instrument with a ``price_stats@v2`` row (as ``dividends@v2``).

The corporate-actions task fetches the window ``-7..+30`` days around each session and stores
what it got in that session's partition, so a declared future ex-date is stored from the
first session whose window reached it and is known from then on (a dividend declared later is
not known earlier: the snapshot rule, ADR 0007). On session S:

- the candidates are the rows stored on or before S whose ex-date (``ts``) is after S, the
  latest stored version of each (instrument, ex-date);
- a row an instrument's latest such partition no longer lists was moved or withdrawn, and is
  ignored (an ex-date listed by an older partition only is never "next"); a date a later fetch
  dropped with nothing replacing it stays until it passes, because an empty fetch stores
  nothing to say so;
- the NEXT ex-date is the earliest candidate. Every distribution type counts (a special
  dividend is also an ex-date a short call must survive), unlike ``dividends@v2``'s yield.

    dividend_status  SCHEDULED (an ex-date after the session is known on it) or NOT_ANNOUNCED
                     (none: a payer between declarations, or a non-payer; never null)
    next_ex_date     the next ex-dividend date
    next_div_amount  its cash amount per share, in the session's share terms: divided by the
                     ratio of every split with an event date in (the partition that stored it,
                     the session] (the partition's number is in the share terms of its day)
    days_to_ex_date  calendar days from the session to the ex-date (>= 1)
    next_pay_date    its payment date; null when the source gives none

A date after the session is only listed from 30 days before it, so NOT_ANNOUNCED is "none in
the next ~30 days", not "none this quarter": ``days_to_ex_date`` above 30 never occurs. History
before the first stored partition has no row to read, so backfilled sessions older than the
store read NOT_ANNOUNCED.
"""

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature, NullReason
from algotrade.features.rollups.corporate.dividends import PRICE_STATS, SPLITS, split_factors

NAME = "dividend_schedule"
VERSION = 1
DECLARED = "events/dividend_declared"
SCHEDULED, NOT_ANNOUNCED = "SCHEDULED", NullReason.NOT_ANNOUNCED.value
LOOKBACK = 60  # sessions of splits: more than the 30-day window a declared row is stored in

_NONE = (
    "no ex-dividend date after the session in the dividend rows stored by it (dividend_status "
    "NOT_ANNOUNCED)"
)
_EXPLAINED: dict[str, Any] = {
    "null_status": "dividend_status",
    "explained_statuses": (NOT_ANNOUNCED,),
}

FEATURES = (
    Feature(
        "dividend_status", "str", "category",
        "SCHEDULED: an ex-dividend date after the session is known on it; NOT_ANNOUNCED: none "
        "(a payer between declarations, or a non-payer)",
        "never", "label", categories=(SCHEDULED, NOT_ANNOUNCED),
        inputs=(f"{DECLARED}.ts",),
    ),
    Feature(
        "next_ex_date", "date", "date",
        "The next ex-dividend date after the session, as known on the session",
        _NONE, inputs=(f"{DECLARED}.ts",), **_EXPLAINED,
    ),
    Feature(
        "next_div_amount", "float32", "usd_per_share",
        "The next dividend's cash amount per share, in the session's share terms (divided by "
        "the splits since the partition that stored it)",
        _NONE, valid_range=(0, None), inputs=(f"{DECLARED}.cash_amount", f"{SPLITS}.ratio"),
        **_EXPLAINED,
    ),
    Feature(
        "days_to_ex_date", "int", "days",
        "Calendar days from the session to the next ex-dividend date",
        _NONE, valid_range=(1, None), inputs=(f"{DECLARED}.ts",), **_EXPLAINED,
    ),
    Feature(
        "next_pay_date", "date", "date", "The next dividend's payment date",
        f"{_NONE}, or the source gives no payment date for it", inputs=(f"{DECLARED}.pay_date",),
        **_EXPLAINED,
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _pay_dates(rows: pd.DataFrame) -> list[date | None]:
    if "pay_date" not in rows.columns:
        return [None] * len(rows)
    parsed = pd.to_datetime(rows["pay_date"], errors="coerce")
    return [d.date() if pd.notna(d) else None for d in parsed]


def upcoming(
    declared: pd.DataFrame | None, splits: pd.DataFrame | None, session: date
) -> pd.DataFrame:
    """Per instrument with a known ex-date after ``session``: ``instrument_id``,
    ``next_ex_date``, ``next_div_amount``, ``days_to_ex_date``, ``next_pay_date`` (the module
    doc's rule). ``declared``: ``events/dividend`` rows as stored, each with its
    ``session_date`` (the partition that stored it)."""
    columns = ["instrument_id", "next_ex_date", "next_div_amount", "days_to_ex_date"]
    columns.append("next_pay_date")
    if declared is None or declared.empty:
        return pd.DataFrame(columns=columns)
    rows = declared.assign(
        ex_date=pd.to_datetime(declared["ts"], utc=True).dt.date,
        stored=pd.to_datetime(declared["session_date"]).dt.date,
    )
    rows = rows[(rows["ex_date"] > session) & (rows["stored"] <= session)]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    order = ["stored", *(["knowledge_ts"] if "knowledge_ts" in rows.columns else [])]
    rows = rows.sort_values(order, kind="stable").drop_duplicates(
        ["instrument_id", "ex_date"], keep="last"
    )
    latest = rows.groupby("instrument_id")["stored"].transform("max")
    rows = rows[rows["stored"] == latest]
    first = rows.sort_values(["instrument_id", "ex_date"], kind="stable")
    first = first.drop_duplicates("instrument_id", keep="first")
    # The amount is in the share terms of the day its partition stored it: later splits scale it.
    factor = split_factors(first.assign(event_date=first["stored"]), splits, session)
    return pd.DataFrame(
        {
            "instrument_id": first["instrument_id"].astype(str).to_numpy(),
            "next_ex_date": first["ex_date"].to_numpy(),
            "next_div_amount": first["cash_amount"].to_numpy(dtype=float) / factor,
            "days_to_ex_date": [(d - session).days for d in first["ex_date"]],
            "next_pay_date": _pay_dates(first),
        }
    )


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session][["instrument_id"]]
    nxt = upcoming(inputs.get(DECLARED), inputs.get(SPLITS), session)
    out = today.merge(nxt, on="instrument_id", how="left")
    out["dividend_status"] = np.where(out["next_ex_date"].notna(), SCHEDULED, NOT_ANNOUNCED)
    return out[["instrument_id", *COLUMNS]].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "The next known ex-dividend date, its amount (split-adjusted to the session) and pay date, "
    "as known on the session",
    (
        Input(PRICE_STATS),
        Input(DECLARED, required=False),
        Input(SPLITS, lookback=LOOKBACK, required=False),
    ),
    FEATURES,
    compute,
)
