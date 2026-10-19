"""The comparison of a periodic filing with the same company's year-ago filing, written once.

A subject filing is a 10-K or 10-Q (an amendment, ``10-K/A`` / ``10-Q/A``, is never a subject or
a comparator) of a filer (``cik``). Its comparator is the same company's filing of the same form
whose report date is ``WINDOW_DAYS`` before the subject's (a 10-Q against the same quarter a
year earlier, a 10-K against the previous year's), the closest to 365 days when two qualify. The
pairing is by ``cik`` and ``accession``: the id-fill versions of a stored filing are one filing.

Per item the form declares (``ITEMS``) a pair is compared only when both rows are ``OK`` and each
side has ``MIN_ITEM_TOKENS`` words. The composite sums the term counts of the compared items and
needs ``MIN_COMPOSITE_TOKENS`` words each side. The status says why a value is missing:
``OK``; ``NO_PRIOR`` (no comparator is stored); ``NOT_COMPARABLE`` (no item passes, or the
composite is under the floor). A value is null whenever the status is not ``OK``, never zero.

The measures are ``quant.text``: cosine on raw term counts and Jaccard on word sets. The
risk-factor pair (10-K Item 1A alone) also gives the change in length: new words over old, minus
one.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade.quant.text.similarity import merge_counts, term_cosine, term_jaccard
from algotrade.quant.text.tokens import term_counts

TEN_K = "10-K"
TEN_Q = "10-Q"
PERIODIC = (TEN_K, TEN_Q)
ITEMS = {TEN_K: ("1", "1A", "3", "7"), TEN_Q: ("I-2", "II-1A")}
RISK_ITEM = "1A"
MIN_ITEM_TOKENS = 100
MIN_COMPOSITE_TOKENS = 500
WINDOW_DAYS = (330, 400)  # the comparator's report date, days before the subject's
YEAR_DAYS = 365
RECENT_SESSIONS = 5  # a filing is a subject for this many sessions after it became known
OK = "OK"
NO_PRIOR = "NO_PRIOR"
NOT_COMPARABLE = "NOT_COMPARABLE"
OK_QUALITY = "OK"  # equals data.filing_text.reading.OK (tested)


@dataclass(frozen=True)
class Comparison:
    """One subject filing against its comparator (module doc); the measures are null unless
    ``status`` is ``OK``."""

    cik: str
    accession: str
    prior_accession: str | None
    form: str
    known_from: date
    status: str
    cosine: float | None = None
    jaccard: float | None = None
    items_compared: int | None = None
    rf_cosine: float | None = None
    rf_len_change: float | None = None


def _day(value: Any) -> date | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).date()


def _filings(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per periodic (cik, accession): form, report date and ``known_from``, the session
    the filing was accepted into (``accepted_session``, the earliest over its item rows), never the
    day a parser re-run re-stored it."""
    rows = frame[frame["form"].isin(PERIODIC)]
    keep = ["cik", "accession", "form", "report_date"]
    out = rows[keep].drop_duplicates(["cik", "accession"]).copy()
    first: dict[tuple[str, str], date] = {}
    for cik, accession, value in zip(
        rows["cik"], rows["accession"], rows["accepted_session"], strict=True
    ):
        day = _day(value)
        if day is not None:
            first[(cik, accession)] = min(day, first.get((cik, accession), day))
    out["report_date"] = [_day(v) for v in out["report_date"]]
    out["known_from"] = [first[(c, a)] for c, a in zip(out["cik"], out["accession"], strict=True)]
    return out.sort_values(["cik", "known_from", "accession"], kind="stable")


def _item_counts(
    frame: pd.DataFrame, cik: str, accession: str, form: str
) -> dict[str, Counter[str]]:
    """The term counts of each item of one filing that passes the quality and length floors."""
    rows = frame[(frame["cik"] == cik) & (frame["accession"] == accession)]
    out: dict[str, Counter[str]] = {}
    for item, quality, text in zip(rows["item"], rows["quality"], rows["text"], strict=True):
        if item not in ITEMS[form] or quality != OK_QUALITY or not isinstance(text, str):
            continue
        counts = term_counts(text)
        if sum(counts.values()) >= MIN_ITEM_TOKENS:
            out[str(item)] = counts
    return out


def _comparator(filings: pd.DataFrame, subject: pd.Series) -> pd.Series | None:
    """The year-ago filing of the same company and form (module doc), or ``None``."""
    report = subject["report_date"]
    if report is None:
        return None
    low, high = (report - timedelta(days=d) for d in WINDOW_DAYS[::-1])
    same = filings[(filings["cik"] == subject["cik"]) & (filings["form"] == subject["form"])]
    same = same[[r is not None and low <= r <= high for r in same["report_date"]]]
    same = same[same["accession"] != subject["accession"]]
    if same.empty:
        return None
    gap = [abs((report - r).days - YEAR_DAYS) for r in same["report_date"]]
    best: pd.Series = (
        same.assign(_gap=gap).sort_values(["_gap", "accession"], kind="stable").iloc[0]
    )
    return best


def _measure(
    new: dict[str, Counter[str]], old: dict[str, Counter[str]], form: str
) -> dict[str, Any]:
    shared = sorted(new.keys() & old.keys())
    if not shared:
        return {"status": NOT_COMPARABLE}
    a = merge_counts([new[i] for i in shared])
    b = merge_counts([old[i] for i in shared])
    if sum(a.values()) < MIN_COMPOSITE_TOKENS or sum(b.values()) < MIN_COMPOSITE_TOKENS:
        return {"status": NOT_COMPARABLE}
    out: dict[str, Any] = {
        "status": OK,
        "cosine": term_cosine(a, b),
        "jaccard": term_jaccard(a, b),
        "items_compared": len(shared),
    }
    if form == TEN_K and RISK_ITEM in shared:
        out["rf_cosine"] = term_cosine(new[RISK_ITEM], old[RISK_ITEM])
        out["rf_len_change"] = sum(new[RISK_ITEM].values()) / sum(old[RISK_ITEM].values()) - 1.0
    return out


def compare_filings(frame: pd.DataFrame, recent_from: date, session: date) -> list[Comparison]:
    """The comparison of each company's latest periodic filing known from ``recent_from`` to
    ``session`` (latest acceptance session, then accession) with its comparator among the filings
    of ``frame`` (rows ``cik``, ``form``, ``accession``, ``report_date``, ``accepted_session``,
    ``item``, ``quality``, ``text``), one per ``cik``, sorted by ``cik``."""
    filings = _filings(frame)
    subjects = filings[[recent_from <= k <= session for k in filings["known_from"]]]
    subjects = subjects.drop_duplicates("cik", keep="last")
    out = []
    for _, subject in subjects.iterrows():
        base: dict[str, Any] = {"cik": subject["cik"], "accession": subject["accession"],
                "form": subject["form"], "known_from": subject["known_from"]}  # fmt: skip
        prior = _comparator(filings, subject)
        if prior is None:
            out.append(Comparison(**base, prior_accession=None, status=NO_PRIOR))
            continue
        new = _item_counts(frame, subject["cik"], subject["accession"], subject["form"])
        old = _item_counts(frame, prior["cik"], prior["accession"], prior["form"])
        out.append(
            Comparison(
                **base, prior_accession=prior["accession"], **_measure(new, old, subject["form"])
            )
        )
    return out
