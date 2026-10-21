"""SEC EDGAR 10-K / 10-Q documents -> their item sections (edge build D10; free, no key).

One request per filing: the ``primaryDocument`` of the submissions JSON (``submissions.py``), an
inline-XBRL HTML file of 0.3-10 MB, at
``https://www.sec.gov/Archives/edgar/data/<cik>/<accession without dashes>/<primaryDocument>``.
Same pacing, ``User-Agent`` and ``sec`` limiter as the other SEC sources (``[sec_edgar]``,
10 requests a second at most).

**The payload is the extraction, never the HTML.** ``fetch`` downloads the document, runs
``filing_items.extract_text`` and returns a compact JSON document (the accession, the form, the
parser version and the item rows); ``normalize`` rebuilds the frame from it alone. The HTML is
dropped after parsing: 100+ GB over the history, never committed, and the parser is deterministic,
so a new parser version is a refetch. The task saves no raw copy (it would be the table again).

**Failure is an error, never an empty answer.** A 404, an empty body or a block page raises (the
task fails the item and a rerun asks again). A short document or one with no item header (an
exhibit-only 10-K/A) is an answer: one ``NO_ITEMS`` row, or ``SHORT`` sections, never guessed text.

``normalize`` returns ``parsed["filing_text"]`` (``FILING_TEXT_COLUMNS``), one row per item kept:
``item``, ``text``, ``char_count``, ``quality``, ``reason``, ``method``, ``parser_version``.
Point-in-time stamping (``known_from``) and the instrument id belong to the task.
"""

import json
import re
from typing import Any

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized, TransientFetchError
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.series import (
    FILING_TEXT_COLUMNS,
    FILING_TEXT_FRAME,
    FilingTextRequest,
    items_for,
)
from algotrade_sources.vendors.sec_text.filing_items import (
    PARSER_VERSION,
    extract_text,
    html_to_text,
)

SOURCE = "sec_edgar"
DATASET = "filing_text"
DOCUMENT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
_DOCUMENT = re.compile(
    r"[A-Za-z0-9][\w.\-]*\.(?:htm|html|txt)", re.IGNORECASE
)  # a file name, never a path; pre-2015 filings use ``.HTM``
_BLOCKED = (b"Request Rate Threshold", b"Undeclared Automated Tool")  # SEC's 200-status block pages


def filing_text_request(request: FetchRequest) -> FilingTextRequest:
    """``request`` as a ``FilingTextRequest`` (this source takes no other kind)."""
    if not isinstance(request, FilingTextRequest):
        raise TypeError(f"SEC filing text needs a FilingTextRequest, got {type(request).__name__}")
    return request


def document_url(request: FilingTextRequest) -> str:
    """The archive URL of the request's primary document; a malformed accession, CIK or file name
    (it would leave the filing's folder) is an error."""
    cik = pad_cik(request.cik)
    if cik is None or _ACCESSION.fullmatch(request.key) is None:
        raise ValueError(f"not a CIK / accession: {request.cik!r} / {request.key!r}")
    if _DOCUMENT.fullmatch(request.primary_document) is None:
        raise ValueError(f"unexpected primary document name: {request.primary_document!r}")
    return DOCUMENT_URL.format(
        cik=int(cik), accession=request.key.replace("-", ""), document=request.primary_document
    )


def parse_payload(payload: bytes) -> pd.DataFrame:
    """The extraction document ``fetch`` saved -> the item rows (``FILING_TEXT_COLUMNS``)."""
    document: dict[str, Any] = json.loads(payload)
    rows = document.get("items")
    if not isinstance(rows, list) or not rows:
        raise ValueError("filing text answer has no item rows")
    frame = pd.DataFrame(rows, columns=list(FILING_TEXT_COLUMNS))
    return frame.astype({"char_count": "int64", "parser_version": "int64"}).reset_index(drop=True)


def extract_payload(body: bytes, accession: str, form: str, items: tuple[str, ...]) -> bytes:
    """The extraction document of one downloaded filing (module doc): pure, so a worker process
    can run it; ``fetch`` is ``fetch_body`` then this."""
    text = html_to_text(body)
    rows = extract_text(text, form, items_for(form, items))
    document = {
        "accession": accession,
        "form": form,
        "parser_version": PARSER_VERSION,
        "document_bytes": len(body),
        "items": rows,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class SecFilingText:
    """Implements ``sources.base.Source``. Request: a ``FilingTextRequest`` (``key`` = the
    accession, ``cik``, ``form``, ``primary_document``, the ``items`` kept)."""

    name = SOURCE
    dataset = DATASET
    parse = staticmethod(extract_payload)  # the pure half of ``fetch``, runnable in a worker

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def fetch_body(self, request: FetchRequest) -> bytes | None:
        """The primary document as SEC serves it (``None``: a 404); an empty body or a block
        page raises. The download half of ``fetch``, for a caller that parses elsewhere (a
        process pool: ``extract_payload`` is pure and takes only plain values)."""
        wanted = filing_text_request(request)
        body = self._http.get(document_url(wanted))
        if body is None:
            return None
        if not body.strip() or any(mark in body[:20_000] for mark in _BLOCKED):
            raise TransientFetchError(f"SEC document {wanted.key}: empty or a block page")
        return body

    def fetch(self, request: FetchRequest) -> bytes | None:
        wanted = filing_text_request(request)
        body = self.fetch_body(wanted)
        if body is None:
            return None
        return extract_payload(body, wanted.key, wanted.form, wanted.items)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=None, tables={}, parsed={FILING_TEXT_FRAME: parse_payload(payload)}
        )
