"""SEC EDGAR full-text search for the 424B4 final prospectuses that mention a lock-up (ADR 0050,
edge build D8; free, no key).

``https://efts.sec.gov/LATEST/search-index?q="lock-up"&forms=424B4&dateRange=custom&startdt=..&enddt=..``
answers (JSON, measured 2026-10-17: 33 hits for 2026-09-01..10-17) with ``hits.total.value`` and
``hits.hits[]._source`` holding ``adsh`` (the accession number), ``ciks`` (the filer first),
``display_names``, ``file_date`` and ``form``. It is the one way to list prospectuses BY FORM
across every issuer, a new IPO that is in no universe yet included (the submissions JSON of
``submissions.py`` is per CIK). The endpoint is public and used by SEC's own search page but not
documented as an API: same ``User-Agent`` (contact from ``ALGOTRADE_SEC_CONTACT``), the shared
``sec`` limiter (``[sec_edgar]``, well under 10 requests/second) and no crawling beyond the
windows asked. Nasdaq's IPO calendar is deliberately not used: its terms forbid automated capture.

``fetch`` pages through one window (100 hits a page, ``from`` = the offset) and saves the pages
one JSON document after another (``framework/pages.py``). The search returns at most 10,000
hits, so a window with more is an error (the caller asks months, never years). ``normalize``
returns ``parsed["prospectus_hits"]`` (``HIT_COLUMNS``): one row per accession (a filing with
several matching documents is one), ``cik`` 10 digits, ``name`` the issuer's without the ticker
and CIK EDGAR appends, ``filing_date`` a calendar day, sorted by
(``filing_date``, ``accession``).

Recall: the query is the phrase ``"lock-up"`` (the verified form). A prospectus that spells it
only ``lockup`` is not listed; the task's stats say how many 424B4 it saw per window, so a gap
shows against D1's ``events/filing`` 424B4 rows.
"""

import json
import re
import urllib.parse
from datetime import date
from typing import Any

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.pages import json_documents
from algotrade_sources.framework.series import HIT_COLUMNS, HITS_FRAME, ProspectusSearchRequest

SOURCE = "sec_edgar"
DATASET = "prospectus_search"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
QUERY = '"lock-up"'
FORM = "424B4"
PAGE_SIZE = 100
MAX_HITS = 10_000  # the search never serves a hit past this offset
_SUFFIX = re.compile(r"(?:\s*\([^)]*\))+\s*$")  # "Foo Inc.  (FOO)  (CIK 0001234567)"


def search_request(request: FetchRequest) -> ProspectusSearchRequest:
    """``request`` as a ``ProspectusSearchRequest`` (this source takes no other kind)."""
    if not isinstance(request, ProspectusSearchRequest):
        raise TypeError(f"SEC search needs a ProspectusSearchRequest, got {type(request).__name__}")
    return request


def search_url(start: date, end: date, offset: int) -> str:
    """The search of one window's page starting at hit ``offset``."""
    query = urllib.parse.urlencode(
        {
            "q": QUERY,
            "forms": FORM,
            "dateRange": "custom",
            "startdt": start.isoformat(),
            "enddt": end.isoformat(),
            "from": offset,
            "size": PAGE_SIZE,
        }
    )
    return f"{SEARCH_URL}?{query}"


def _total(document: dict[str, Any]) -> int:
    total = document.get("hits", {}).get("total", {})
    if not isinstance(total, dict) or not isinstance(total.get("value"), int):
        raise ValueError("SEC search answer has no hits.total.value")
    return int(total["value"])


def parse_hits(payload: bytes) -> pd.DataFrame:
    """The 424B4 hits of every page in ``payload``, one row per accession (``HIT_COLUMNS``)."""
    rows = []
    for document in json_documents(payload, "SEC search"):
        _total(document)
        for hit in document["hits"].get("hits") or []:
            source = hit.get("_source") or {}
            ciks = source.get("ciks") or []
            names = source.get("display_names") or []
            cik = pad_cik(ciks[0]) if ciks else None
            if cik is None or not source.get("adsh") or not source.get("file_date"):
                raise ValueError(f"SEC search hit without a filer, accession or date: {hit!r:.120}")
            if source.get("form") != FORM:  # the query names the form; a variant is not asked for
                continue
            rows.append(
                {
                    "cik": cik,
                    "accession": str(source["adsh"]),
                    "filing_date": pd.to_datetime(source["file_date"]),
                    "name": " ".join(_SUFFIX.sub("", str(names[0])).split()) or None
                    if names
                    else None,
                }
            )
    frame = pd.DataFrame(rows, columns=list(HIT_COLUMNS))
    frame["filing_date"] = frame["filing_date"].astype("datetime64[ns]")
    frame = frame.sort_values(["filing_date", "accession"], kind="stable")
    return frame.drop_duplicates("accession").reset_index(drop=True)


class SecProspectusSearch:
    """Implements ``sources.base.Source``. Request: a ``ProspectusSearchRequest``."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def fetch(self, request: FetchRequest) -> bytes | None:
        ask = search_request(request)
        first = self._http.get(search_url(ask.start, ask.end, 0))
        if first is None:
            return None
        total = _total(json.loads(first))
        if total > MAX_HITS:
            raise ValueError(f"SEC search lists {total} hits for {ask.key}: ask a shorter window")
        pages = [first]
        for offset in range(PAGE_SIZE, total, PAGE_SIZE):
            page = self._http.get(search_url(ask.start, ask.end, offset))
            if page is None:  # the first page just answered: a vanished page is not "no hits"
                raise ValueError(f"SEC search page {offset} of {ask.key} gone")
            pages.append(page)
        return b"\n".join(pages)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(session_date=None, tables={}, parsed={HITS_FRAME: parse_hits(payload)})
