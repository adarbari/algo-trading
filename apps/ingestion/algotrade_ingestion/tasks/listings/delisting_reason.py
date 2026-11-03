"""Why a name delisted, from the filings around its last bar, and when that was public (ADR 0087
decision 4): the pure rules behind the ``delistings`` task.

A filing counts when it was accepted in ``[last day - WINDOW_BEFORE, last day + WINDOW_AFTER]``
days. The reason, in order: an 8-K with Item 1.03 (bankruptcy) -> BANKRUPTCY; else 2.01 (a
completed acquisition) or 5.01 (a change in control) -> ACQUIRED; else 3.01 (a failure to
satisfy a listing standard) -> STANDARDS; else a Form 25 filed by the issuer -> VOLUNTARY; else
UNKNOWN. ``known_from`` is the session after the earliest Form 25 or 25-NSE accepted in the
window (the exchange's notice makes the delisting public), else the session after the last bar.
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
FORM_25 = "25"  # filed by the issuer: a voluntary delisting
FORM_25_NSE = "25-NSE"  # filed by the exchange: the notice, whoever caused the delisting
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


def in_window(filings: pd.DataFrame, last_day: date) -> pd.DataFrame:
    """The filings accepted (UTC date of ``ts``) within the window around ``last_day``."""
    day = pd.to_datetime(filings["ts"], utc=True).dt.date
    low, high = last_day - timedelta(WINDOW_BEFORE), last_day + timedelta(WINDOW_AFTER)
    return filings[(day >= low) & (day <= high)]


def _label(row: pd.Series) -> str:
    return f"{row['accession']} {row['form']} {row['items'] or '-'}".strip()


def _items(value: object) -> frozenset[str]:
    return frozenset(i.strip() for i in str(value or "").split(",") if i.strip())


def judge(filings: pd.DataFrame, last_day: date, last_session: date) -> Verdict:
    """The verdict of one instrument: ``filings`` its stored ``events/filing`` rows (any date),
    ``last_day`` the vendor's last trading day, ``last_session`` its last stored bar."""
    window = in_window(filings, last_day)
    forms = window["form"].astype(str)
    notice = window[forms.isin((FORM_25, FORM_25_NSE))]
    if notice.empty:
        known = next_session(last_session)
    else:
        known = next_session(min(acceptance_sessions(notice["ts"])))
    eight_k = window[forms.isin(EIGHT_K)]
    items = eight_k["items"].map(_items)
    for reason, wanted in RULES:
        hit = eight_k[items.map(lambda found, w=wanted: bool(found & w))]
        if not hit.empty:
            return Verdict(reason, "; ".join(hit.apply(_label, axis=1)), known)
    issuer = window[forms.eq(FORM_25)]
    if not issuer.empty:
        return Verdict(VOLUNTARY, "; ".join(issuer.apply(_label, axis=1)), known)
    return Verdict(UNKNOWN, "", known)
