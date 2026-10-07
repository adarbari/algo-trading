"""SEC EDGAR daily form index: the CIKs that filed an 8-K on a day (ADR 0050; free, no key).

``https://www.sec.gov/Archives/edgar/daily-index/<YYYY>/QTR<n>/form.<YYYYMMDD>.idx`` lists every
filing SEC disseminated under that filing date, one fixed-width text line each: form type,
company name, CIK, date filed (``YYYYMMDD``) and the file name
(``edgar/data/<cik>/<accession>.txt``).
It has no items and no acceptance time (the submissions JSON of ``submissions.py`` has both), so
the nightly uses it only to learn WHICH CIKs to ask. ``normalize`` keeps the ``8-K`` and
``8-K/A`` lines as ``parsed["daily_index"]`` (``DAILY_INDEX_COLUMNS``): ``cik`` (10 digits),
``form``, ``accession`` and ``filing_date`` (a calendar day), sorted by accession.

A day without a published index (a weekend, a federal holiday, or a day SEC has not published
yet) is answered 403 with S3's ``AccessDenied`` XML (measured 2026-10-07; 404 is handled as
missing too): ``fetch`` returns ``None``, which the task reads as "no index (yet)", never as an
empty day. A block (HTML) stays an error. Same pacing, ``User-Agent`` and ``sec`` limiter as
the other SEC sources (``[sec_edgar]``).
"""

import re
from datetime import date

import pandas as pd

from algotrade.core.model.instruments import pad_cik
from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http, HttpError
from algotrade_sources.framework.series import (
    DAILY_INDEX_COLUMNS,
    DAILY_INDEX_FRAME,
    DailyIndexRequest,
)
from algotrade_sources.vendors.sec.submissions import FORMS

SOURCE = "sec_edgar"
DATASET = "daily_index"
INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/form.{day}.idx"
_LINE = re.compile(
    r"^(?P<form>\S+)\s+(?P<name>.+?)\s+(?P<cik>\d+)\s+(?P<filed>\d{8})\s+"
    r"edgar/data/\d+/(?P<accession>[\w-]+)\.txt\s*$"
)


def missing_index(exc: HttpError) -> bool:
    """SEC serves the archive from S3: a day with no index answers 403 with S3's ``AccessDenied``
    XML. A block answers with HTML, so it stays an error (and counts for the circuit breaker)."""
    return exc.status == 403 and b"<Code>AccessDenied</Code>" in exc.body


def index_url(day: date) -> str:
    """The URL of the form index filed under ``day``."""
    quarter = (day.month - 1) // 3 + 1
    return INDEX_URL.format(year=day.year, quarter=quarter, day=day.strftime("%Y%m%d"))


def daily_index_request(request: FetchRequest) -> DailyIndexRequest:
    """``request`` as a ``DailyIndexRequest`` (this source takes no other kind)."""
    if not isinstance(request, DailyIndexRequest):
        raise TypeError(f"SEC daily index needs a DailyIndexRequest, got {type(request).__name__}")
    return request


def parse_index(payload: bytes) -> pd.DataFrame:
    """The 8-K and 8-K/A lines of one form index (``DAILY_INDEX_COLUMNS``), sorted by accession.

    A line of those forms that does not match the layout is an error: a silently skipped line
    would be a filer the nightly never asks about."""
    rows = []
    for line in payload.decode("latin-1").splitlines():
        form = line.split(None, 1)[0] if line.strip() else ""
        if form not in FORMS:
            continue
        match = _LINE.match(line)
        if match is None:
            raise ValueError(f"unexpected daily index line: {line[:80]!r}")
        rows.append(
            {
                "cik": pad_cik(match["cik"]),
                "form": form,
                "accession": match["accession"],
                "filing_date": pd.to_datetime(match["filed"], format="%Y%m%d"),
            }
        )
    frame = pd.DataFrame(rows, columns=list(DAILY_INDEX_COLUMNS))
    frame["filing_date"] = frame["filing_date"].astype("datetime64[ns]")
    return frame.sort_values("accession", kind="stable").reset_index(drop=True)


class SecDailyIndex:
    """Implements ``sources.base.Source``. Request: a ``DailyIndexRequest`` (``day``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``sec`` limiter; sets the User-Agent itself

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(index_url(daily_index_request(request).day))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=None, tables={}, parsed={DAILY_INDEX_FRAME: parse_index(payload)}
        )
