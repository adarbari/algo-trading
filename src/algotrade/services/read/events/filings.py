"""An instrument's 8-K and 8-K/A filings (``Filing``, ADR 0050) in a trailing window of months
ending at the session, from ``events/filing`` by acceptance date among the rows known on or
before the session (``known_from``: the acceptance's New York session; ADR 0050 decision 3), so
a past session never shows a filing accepted after it. Each filing's ``label`` names its first
item in words (2.02 results, 5.02 management, ...); the items stay listed as SEC gives them.

Only the event-study scope's filings are fetched (ADR 0050 decision 2): a company with no
filing known by the session at all is UNKNOWN (``NO_ROW``: not fetched, or none filed), so an
empty window is never mistaken for "no filings" of a company we never asked about."""

from calendar import monthrange
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from algotrade.data.events import ALL_TIME, known_from, read_events
from algotrade.services.read.context import ReadContext
from algotrade.services.read.values import Unknown, UnknownCode

FILING_TABLE = "events/filing"
# The first item of an 8-K in words (SEC Form 8-K items); others read "Item <n>".
ITEM_LABELS = {
    "1.01": "Material agreement",
    "1.02": "Agreement terminated",
    "2.01": "Acquisition or disposal",
    "2.02": "Results",
    "2.03": "New debt obligation",
    "2.05": "Restructuring costs",
    "2.06": "Impairment",
    "3.01": "Listing notice",
    "4.02": "Restatement",
    "5.02": "Management change",
    "5.07": "Shareholder vote",
    "7.01": "Guidance / Reg FD",
    "8.01": "Other events",
    "9.01": "Exhibits",
}


@dataclass(frozen=True)
class Filing:
    """One 8-K: ``accepted`` the SEC acceptance instant (UTC), ``filing_date`` the date SEC
    files it under, ``form`` 8-K or 8-K/A, ``items`` as SEC lists them, ``label`` the first
    item in words, ``known_from`` the session it was public on."""

    accepted: datetime
    filing_date: date
    form: str
    items: tuple[str, ...]
    label: str
    known_from: date


def months_before(day: date, months: int) -> date:
    """``day`` ``months`` calendar months earlier (the 31st of a shorter month: its last day)."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def item_label(items: Sequence[str], form: str) -> str:
    """The first item in words (an 8-K with no items: its form)."""
    if not items:
        return form
    return ITEM_LABELS.get(items[0], f"Item {items[0]}")


def _filing(row: Mapping[Any, Any], accepted: pd.Timestamp, known: date) -> Filing:
    items = tuple(i.strip() for i in str(row["items"] or "").split(",") if i.strip())
    form = str(row["form"])
    return Filing(
        accepted=accepted.to_pydatetime(),
        filing_date=pd.Timestamp(row["filing_date"]).date(),
        form=form,
        items=items,
        label=item_label(items, form),
        known_from=known,
    )


def load_filings(
    ctx: ReadContext, instrument_ids: Sequence[str], months: int
) -> tuple[dict[str, tuple[Filing, ...]], dict[str, Unknown]]:
    """Each instrument's filings accepted in the ``months`` before the session through it,
    newest first, and the UNKNOWN of each with no filing known by the session at all: one read
    for them all."""
    day = ctx.session.date
    ids = list(dict.fromkeys(instrument_ids))
    frame = read_events(ctx.reader, FILING_TABLE, *ALL_TIME, ids, through=day).frame
    start = months_before(day, months)
    filings: dict[str, list[Filing]] = {iid: [] for iid in ids}
    seen = {str(i) for i in frame["instrument_id"]}
    if not frame.empty:
        accepted = pd.to_datetime(frame["ts"], utc=True)
        known = known_from(frame).dt.date
        rows = zip(frame.to_dict("records"), accepted, known, strict=True)
        for row, ts, stamp in rows:
            if ts.date() >= start:
                filings.setdefault(str(row["instrument_id"]), []).append(_filing(row, ts, stamp))
    gaps = {
        iid: Unknown(
            UnknownCode.NO_ROW,
            f"{FILING_TABLE} has no filings of {iid} known by {day.isoformat()} "
            "(filings are fetched for the event-study scope only)",
        )
        for iid in ids
        if iid not in seen
    }
    newest = {
        iid: tuple(sorted(found, key=lambda f: f.accepted, reverse=True))
        for iid, found in filings.items()
    }
    return newest, gaps
