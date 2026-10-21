"""The comparison of a periodic filing with the same company's year-ago filing, written once.

A subject filing is a 10-K or 10-Q (an amendment, ``10-K/A`` / ``10-Q/A``, is never a subject or
a comparator) of a filer (``cik``). Its comparator is the same company's filing of the same form
whose report date is ``WINDOW_DAYS`` before the subject's (a 10-Q against the same quarter a
year earlier, a 10-K against the previous year's), the closest to 365 days when two qualify. A
company's latest subject of each form is compared (one comparison per ``cik`` and form), so a
10-K and a 10-Q both accepted in the window are each compared. The pairing is by ``cik`` and
``accession``: the id-fill versions of a stored filing are one filing.

Per item the form declares (``ITEMS``) a pair is compared only when both rows are ``OK`` and each
side has ``MIN_ITEM_TOKENS`` words. The composite sums the term counts of the compared items and
needs ``MIN_COMPOSITE_TOKENS`` words each side. The status says why a value is missing:
``OK``; ``NO_PRIOR`` (no comparator is stored); ``NOT_COMPARABLE`` (no item passes, or the
composite is under the floor). A value is null whenever the status is not ``OK``, never zero.

The measures are ``quant.text``: cosine on raw term counts and Jaccard on word sets. The
risk-factor pair (10-K Item 1A alone) also gives the change in length: new words over old, minus
one.

A pair's measures depend only on the words of the compared items, so they are memoised per process
(``_MEMO``) under the form and each side's (item, text digest) list: a filing that is a subject
for ``RECENT_SESSIONS`` sessions is tokenised once, not once per session. The memo holds a few
floats per pair and is bounded (``MEMO_PAIRS``, least recently used out); a miss recomputes the
same value, so the output never depends on it.
"""

import hashlib
import threading
from collections import Counter, OrderedDict
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
MEMO_PAIRS = 20_000  # memoised pair results kept (a few floats each)


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


Signature = tuple[tuple[str, str], ...]  # (item, digest of its text) per row that is compared
_MEMO: OrderedDict[tuple[str, Signature, Signature], dict[str, Any]] = OrderedDict()
_MEMO_LOCK = threading.Lock()


def _rows_of(frame: pd.DataFrame) -> dict[tuple[str, str], list[int]]:
    """The positions of each (cik, accession)'s rows in ``frame``, in frame order."""
    keys = zip(frame["cik"], frame["accession"], strict=True)
    out: dict[tuple[str, str], list[int]] = {}
    for position, (cik, accession) in enumerate(keys):
        out.setdefault((str(cik), str(accession)), []).append(position)
    return out


def _usable(
    columns: tuple[list[Any], list[Any], pd.Series], rows: list[int], form: str
) -> list[tuple[str, str]]:
    """The (item, text) of one filing's rows that pass the item and quality floors, in order;
    ``columns`` are the frame's item and quality lists and its text series."""
    items, qualities, texts = columns
    wanted = [i for i in rows if items[i] in ITEMS[form] and qualities[i] == OK_QUALITY]
    found = texts.take(wanted).tolist() if wanted else []
    return [(str(items[i]), t) for i, t in zip(wanted, found, strict=True) if isinstance(t, str)]


def _signature(usable: list[tuple[str, str]]) -> Signature:
    return tuple(
        (item, hashlib.blake2b(text.encode(), digest_size=16).hexdigest()) for item, text in usable
    )


def _item_counts(usable: list[tuple[str, str]]) -> dict[str, Counter[str]]:
    """The term counts of each item of one filing that passes the length floor."""
    out: dict[str, Counter[str]] = {}
    for item, text in usable:
        counts = term_counts(text)
        if sum(counts.values()) >= MIN_ITEM_TOKENS:
            out[item] = counts
    return out


def _comparator(
    candidates: list[tuple[date | None, str]], report: date | None, own: str
) -> str | None:
    """The accession of the year-ago filing among the company's filings of the subject's form
    (``candidates``: report date and accession; ``own``, the subject's, is never its own
    comparator; module doc), or ``None``."""
    if report is None:
        return None
    low, high = (report - timedelta(days=d) for d in WINDOW_DAYS[::-1])
    found = [
        (abs((report - r).days - YEAR_DAYS), a)
        for r, a in candidates
        if r is not None and low <= r <= high and a != own
    ]
    return min(found)[1] if found else None


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
    """The comparison of each company's latest filing of each periodic form known from
    ``recent_from`` to ``session`` (latest acceptance session, then accession) with its comparator
    among the filings of ``frame`` (rows ``cik``, ``form``, ``accession``, ``report_date``,
    ``accepted_session``, ``item``, ``quality``, ``text``), one per ``cik`` and form (a 10-K and a
    10-Q of one company both inside the window are both compared), sorted by ``cik``, form."""
    filings = _filings(frame)
    subjects = filings[[recent_from <= k <= session for k in filings["known_from"]]]
    subjects = subjects.sort_values(["cik", "form", "known_from", "accession"], kind="stable")
    subjects = subjects.drop_duplicates(["cik", "form"], keep="last")
    positions = _rows_of(frame)
    by_company: dict[tuple[str, str], list[tuple[date | None, str]]] = {}
    for cik, form, report, accession in zip(
        filings["cik"], filings["form"], filings["report_date"], filings["accession"], strict=True
    ):
        by_company.setdefault((str(cik), str(form)), []).append((report, accession))
    columns = (frame["item"].tolist(), frame["quality"].tolist(), frame["text"])
    positions = _rows_of(frame)
    out = []
    for _, subject in subjects.iterrows():
        base: dict[str, Any] = {"cik": subject["cik"], "accession": subject["accession"],
                "form": subject["form"], "known_from": subject["known_from"]}  # fmt: skip
        form = subject["form"]
        prior = _comparator(
            by_company[(subject["cik"], form)], subject["report_date"], subject["accession"]
        )
        if prior is None:
            out.append(Comparison(**base, prior_accession=None, status=NO_PRIOR))
            continue
        new = _usable(columns, positions.get((subject["cik"], subject["accession"]), []), form)
        old = _usable(columns, positions.get((subject["cik"], prior), []), form)
        out.append(Comparison(**base, prior_accession=prior, **_memoised_measure(new, old, form)))
    return out


def _memoised_measure(
    new: list[tuple[str, str]], old: list[tuple[str, str]], form: str
) -> dict[str, Any]:
    """``_measure`` of the two filings' compared items, from the memo when the same words were
    compared before."""
    key = (form, _signature(new), _signature(old))
    with _MEMO_LOCK:
        hit = _MEMO.get(key)
        if hit is not None:
            _MEMO.move_to_end(key)
            return dict(hit)
    measured = _measure(_item_counts(new), _item_counts(old), form)
    with _MEMO_LOCK:
        _MEMO[key] = measured
        while len(_MEMO) > MEMO_PAIRS:
            _MEMO.popitem(last=False)
    return dict(measured)
