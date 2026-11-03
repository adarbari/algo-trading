"""Why a name delisted, from the filings around its last bar, and when that was public (ADR 0087
decision 4): the pure rules behind the ``delistings`` task.

A filing counts when it was accepted in ``[last bar - WINDOW_BEFORE, last bar + WINDOW_AFTER]``
days. The reason, in order: an 8-K with Item 1.03 (bankruptcy) -> BANKRUPTCY; else 2.01 (a
completed acquisition) or 5.01 (a change in control) -> ACQUIRED; else 3.01 (a failure to
satisfy a listing standard) -> STANDARDS; else a Form 25 filed by the issuer (or its amendment)
-> VOLUNTARY; else UNKNOWN.

``known_from`` is the session after the LATER of two things: the earliest notice (Form 25 or
25-NSE, or an amendment) accepted in the window, else the last bar; and the acceptance session of
the filings that decided the reason: a row is never public before the filing it was judged from.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from algotrade.core.time.calendar import next_session
from algotrade.data.events import acceptance_sessions
from algotrade.data.listings.delistings import (
    ACQUIRED,
    BANKRUPTCY,
    STANDARDS,
    UNKNOWN,
    VOLUNTARY,
)

WINDOW_BEFORE = 120  # days before the last trading day
WINDOW_AFTER = 30  # days after it
EIGHT_K = ("8-K", "8-K/A")
ISSUER_FORM_25 = ("25", "25/A")  # filed by the issuer: a voluntary delisting
NOTICES = (*ISSUER_FORM_25, "25-NSE", "25-NSE/A")  # the notice, whoever caused the delisting
RULES: tuple[tuple[str, frozenset[str]], ...] = (
    (BANKRUPTCY, frozenset({"1.03"})),
    (ACQUIRED, frozenset({"2.01", "5.01"})),
    (STANDARDS, frozenset({"3.01"})),
)


@dataclass(frozen=True)
class Verdict:
    reason: str
    reason_source: str  # the filing(s) that decided it ("<accession> <form> <items>"), or ""
    known_from: date


def in_window(filings: pd.DataFrame, last_session: date) -> pd.DataFrame:
    """The filings accepted (UTC date of ``ts``) within the window around ``last_session``."""
    day = pd.to_datetime(filings["ts"], utc=True).dt.date
    low, high = last_session - timedelta(WINDOW_BEFORE), last_session + timedelta(WINDOW_AFTER)
    return filings[(day >= low) & (day <= high)]


def _label(row: pd.Series) -> str:
    return f"{row['accession']} {row['form']} {row['items'] or '-'}".strip()


def _items(value: object) -> frozenset[str]:
    return frozenset(i.strip() for i in str(value or "").split(",") if i.strip())


def _decided(rows: pd.DataFrame) -> tuple[str, date]:
    """The accessions that decided a reason and the latest session any of them became known."""
    return "; ".join(rows.apply(_label, axis=1)), max(acceptance_sessions(rows["ts"]))


def judge(filings: pd.DataFrame, last_session: date) -> Verdict:
    """The verdict of one instrument: ``filings`` its stored ``events/filing`` rows (any date),
    ``last_session`` its last stored bar (the window's anchor)."""
    window = in_window(filings, last_session)
    forms = window["form"].astype(str)
    notice = window[forms.isin(NOTICES)]
    public = last_session if notice.empty else min(acceptance_sessions(notice["ts"]))
    eight_k = window[forms.isin(EIGHT_K)]
    items = eight_k["items"].map(_items)
    decided: tuple[str, str, date] | None = None
    for reason, wanted in RULES:
        hit = eight_k[items.map(lambda found, w=wanted: bool(found & w))]
        if not hit.empty:
            decided = (reason, *_decided(hit))
            break
    if decided is None and not (issuer := window[forms.isin(ISSUER_FORM_25)]).empty:
        decided = (VOLUNTARY, *_decided(issuer))
    if decided is None:
        return Verdict(UNKNOWN, "", next_session(public))
    reason, source, session = decided
    return Verdict(reason, source, next_session(max(public, session)))
