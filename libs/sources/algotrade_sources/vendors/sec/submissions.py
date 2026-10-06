"""SEC EDGAR submissions as a filing history: the 8-Ks a company filed, with the second each
was accepted (ADR 0050; free, no key).

``https://data.sec.gov/submissions/CIK##########.json`` holds a company's most recent filings
(about 1,000, ``filings.recent``) as parallel arrays (``form``, ``filingDate``,
``acceptanceDateTime`` in UTC, ``items`` such as ``"2.02,9.01"``, ...) and names the older ones
in ``filings.files``: pages ``CIK##########-submissions-NNN.json`` under the same directory,
each with the same arrays at the top level and a ``filingFrom`` / ``filingTo`` range. (The
company-details reader of the same document is ``edgar.SecSubmissions``; this module reads the
filings, so its raw dataset is ``filings``.)

``FilingsRequest.since`` is how far back the caller wants filings. ``fetch`` reads the recent
block; only when ``since`` is before its oldest filing does it also read the older pages that
reach ``since`` (``filingTo >= since``), one request each. A single document is saved as
received; with pages they are saved one document after another (one per line), which
``normalize`` reads the same way. Every form stays in the raw payload; ``normalize`` keeps the
``8-K`` and ``8-K/A`` rows filed on or after ``since``. Same pacing, ``User-Agent`` (contact from
``ALGOTRADE_SEC_CONTACT``) and 404 rule as the other SEC sources (the ``sec`` limiter,
``[sec_edgar]``; 404: no filings for this CIK, ``None``).

``normalize`` returns ``parsed["filings"]`` (``FILING_COLUMNS``) sorted by acceptance: ``cik``
(10 digits), ``form``, ``accession``, ``filing_date`` and ``report_date`` (calendar days;
``report_date`` is null when SEC gives none), ``acceptance_ts`` (a UTC timestamp),
``items`` (the string as SEC gives it) and ``primary_document``. Point-in-time stamping and the
instrument id belong to the task.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, NoReturn

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import (
    FetchRequest,
    Normalized,
    TransientFetchError,
)
from algotrade_sources.framework.http import Http

SOURCE = "sec_edgar"
DATASET = "filings"
FILINGS_FRAME = "filings"  # key of ``Normalized.parsed`` holding the normalised frame
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
PAGES_URL = "https://data.sec.gov/submissions/{name}"
PAGE_NAME = re.compile(r"CIK\d{10}-submissions-\d+\.json")  # a page stays under submissions/
FORMS = ("8-K", "8-K/A")
FILING_COLUMNS = (
    "cik",
    "form",
    "accession",
    "filing_date",
    "acceptance_ts",
    "report_date",
    "items",
    "primary_document",
)
_ARRAYS = {  # our column -> the submissions array
    "form": "form",
    "accession": "accessionNumber",
    "filing_date": "filingDate",
    "acceptance_ts": "acceptanceDateTime",
    "report_date": "reportDate",
    "items": "items",
    "primary_document": "primaryDocument",
}


@dataclass(frozen=True, kw_only=True)
class FilingsRequest(FetchRequest):
    """One company's filings. ``key`` is the CIK (digits); ``since``: the earliest filing date
    wanted (``None``: the recent block only)."""

    since: date | None = None


def filings_request(request: FetchRequest) -> FilingsRequest:
    """``request`` as a ``FilingsRequest`` (a plain ``FetchRequest`` has no ``since``)."""
    if isinstance(request, FilingsRequest):
        return request
    return FilingsRequest(
        key=request.key, instrument_id=request.instrument_id, session_date=request.session_date
    )


def parse_documents(payload: bytes) -> list[dict[str, Any]]:
    """The JSON documents in ``payload`` (the company's, then one per older page)."""
    text, decoder, pos, documents = payload.decode("utf-8-sig"), json.JSONDecoder(), 0, []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        try:
            document, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError as exc:
            raise ValueError(f"SEC answer is not JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise ValueError("SEC answer is not a JSON object")
        documents.append(document)
    if not documents:
        raise ValueError("SEC answer is empty")
    return documents


def _recent(document: dict[str, Any]) -> dict[str, Any]:
    """The filing arrays of a submissions document (``filings.recent``) or of an older page
    (the document itself)."""
    filings = document.get("filings")
    block = filings["recent"] if isinstance(filings, dict) and "recent" in filings else document
    if not isinstance(block.get("form"), list):
        raise ValueError("SEC answer has no filing arrays")
    return block


def older_pages(document: dict[str, Any], since: date | None) -> list[str]:
    """The names of the older pages ``since`` needs: none unless ``since`` is before the recent
    block's oldest filing, then every page whose ``filingTo`` reaches ``since`` (a page
    without a range is read)."""
    filings = document.get("filings")
    files = filings.get("files") if isinstance(filings, dict) else None
    if since is None or not files:
        return []
    dates = _recent(document).get("filingDate") or []
    if dates and since >= date.fromisoformat(min(dates)):
        return []
    names = []
    for entry in files:
        name = str(entry.get("name", ""))
        if not PAGE_NAME.fullmatch(name):
            raise ValueError(f"unexpected submissions page name: {name!r}")
        if entry.get("filingTo") is None or date.fromisoformat(entry["filingTo"]) >= since:
            names.append(name)
    return names


def parse_filings(payload: bytes, since: date | None = None) -> pd.DataFrame:
    """The 8-K and 8-K/A rows (``FILING_COLUMNS``) of every document in ``payload`` filed on
    or after ``since``, sorted by acceptance."""
    parts = []
    cik: str | None = None
    for document in parse_documents(payload):
        block = _recent(document)
        if "cik" in document:  # an older page does not repeat the company
            cik = pad_cik(document["cik"])
        columns = {col: block.get(name) or [] for col, name in _ARRAYS.items()}
        size = len(block["form"])
        if any(len(values) not in (0, size) for values in columns.values()):
            raise ValueError("SEC filing arrays differ in length")
        parts.append(pd.DataFrame({c: v or [None] * size for c, v in columns.items()}))
    if cik is None:
        raise ValueError("submissions document has no CIK")
    frame = pd.concat(parts, ignore_index=True)
    frame = frame[frame["form"].isin(FORMS)]
    out = pd.DataFrame(
        {
            "cik": cik,
            "form": frame["form"].astype(str),
            "accession": frame["accession"].astype(str),
            "filing_date": pd.to_datetime(frame["filing_date"]).astype("datetime64[ns]"),
            "acceptance_ts": pd.to_datetime(frame["acceptance_ts"], utc=True).astype(
                "datetime64[ns, UTC]"
            ),
            "report_date": pd.to_datetime(frame["report_date"], errors="coerce").astype(
                "datetime64[ns]"
            ),
            "items": frame["items"].astype(object).where(frame["items"].notna(), ""),
            "primary_document": frame["primary_document"],
        },
        columns=list(FILING_COLUMNS),
    )
    if since is not None:
        out = out[out["filing_date"] >= pd.Timestamp(since)]
    out = out.sort_values(["acceptance_ts", "accession"], kind="stable")
    return out.drop_duplicates("accession").reset_index(drop=True)


class SecFilings:
    """Implements ``sources.base.Source``. Request: a ``FilingsRequest`` (``key`` = a CIK in
    any form, padded to 10 digits; ``since``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def fetch(self, request: FetchRequest) -> bytes | None:
        filings = filings_request(request)
        cik = pad_cik(filings.key)
        if cik is None:
            raise ValueError(f"not a CIK: {filings.key!r}")
        body = self._http.get(SUBMISSIONS_URL.format(cik=cik))
        if body is None:
            return None
        pages = [self._page(name) for name in older_pages(parse_documents(body)[0], filings.since)]
        return b"\n".join([body, *pages]) if pages else body

    def _page(self, name: str) -> bytes:
        page = self._http.get(PAGES_URL.format(name=name))
        if page is None:  # named by the company's own document a moment ago
            _gone(name)
        return page

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_filings(payload, filings_request(request).since)
        return Normalized(session_date=None, tables={}, parsed={FILINGS_FRAME: frame})


def _gone(name: str) -> NoReturn:
    raise TransientFetchError(f"SEC submissions page {name} gone")
