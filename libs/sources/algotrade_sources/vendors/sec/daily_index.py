"""SEC EDGAR daily form index: the CIKs that filed an event form (``submissions.FORMS``, or the
``forms`` of the request: the insider task asks for ``4`` and ``4/A``) on a day (ADR 0050; free,
no key).

``https://www.sec.gov/Archives/edgar/daily-index/<YYYY>/QTR<n>/form.<YYYYMMDD>.idx`` lists every
filing SEC disseminated under that filing date, one fixed-width text line each: form type,
company name, CIK, date filed (``YYYYMMDD``) and the file name
(``edgar/data/<cik>/<accession>.txt``).
It has no items and no acceptance time (the submissions JSON of ``submissions.py`` has both), so
the nightly uses it only to learn WHICH CIKs to ask. ``normalize`` keeps the lines of the
request's forms (default ``FORMS``) as ``parsed["daily_index"]`` (``DAILY_INDEX_COLUMNS``): ``cik``
(10 digits), ``form``, ``accession`` and ``filing_date`` (a calendar day), sorted by accession.

A day without a published index (a weekend, a federal holiday, or a day SEC has not published
yet) is answered 403 with S3's ``AccessDenied`` XML (measured 2026-10-07; 404 is handled as
missing too): ``fetch`` returns ``None``, which the task reads as "no index (yet)", never as an
empty day. A block (HTML) stays an error. Same pacing, ``User-Agent`` and ``sec`` limiter as
the other SEC sources (``[sec_edgar]``).
"""

import functools
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


@functools.cache
def line_patterns(forms: tuple[str, ...]) -> tuple[re.Pattern[str], re.Pattern[str]]:
    """The patterns of the start of a line of ``forms`` and of the whole line. A form type can
    hold a space ("NT 10-K"), so the line starts with a known form, longest first (``25`` is
    not ``25-NSE``, ``4`` is not ``424B4``, ``SC TO-I`` is not its amendment): the type then
    ends at whitespace."""
    alternatives = "|".join(re.escape(f) for f in sorted(forms, key=len, reverse=True))
    return (
        re.compile(rf"^(?:{alternatives})(?=\s)"),
        re.compile(
            rf"^(?P<form>{alternatives})\s+(?P<name>.+?)\s+(?P<cik>\d+)\s+"
            r"(?P<filed>\d{8})\s+edgar/data/\d+/(?P<accession>[\w-]+)\.txt\s*$"
        ),
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


def parse_index(payload: bytes, forms: tuple[str, ...] = FORMS) -> pd.DataFrame:
    """The ``forms`` lines of one form index (``DAILY_INDEX_COLUMNS``), sorted by accession.

    A line of those forms that does not match the layout is an error: a silently skipped line
    would be a filer the nightly never asks about."""
    rows = []
    start, whole = line_patterns(forms)
    for line in payload.decode("latin-1").splitlines():
        if start.match(line) is None:
            continue
        match = whole.match(line)
        if match is None:
            raise ValueError(f"unexpected daily index line: {line[:80]!r}")
        rows.append(
            {
                "cik": pad_cik(match["cik"]),
                "form": match["form"],
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
        frame = parse_index(payload, daily_index_request(request).forms)
        return Normalized(session_date=None, tables={}, parsed={DAILY_INDEX_FRAME: frame})
