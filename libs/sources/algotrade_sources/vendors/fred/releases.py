"""FRED ``release/dates``: the dates a data release was, or is scheduled to be, published
(ADR 0050).

``GET <base_url>/release/dates?release_id=<id>&include_release_dates_with_no_data=true
&file_type=json&limit=10000&offset=<n>[&realtime_start=<start>&realtime_end=<end>]`` (the same
free key as the observations). ``include_release_dates_with_no_data=true`` is what makes FRED
list the scheduled future dates (CPI, release 10: the next ones as of 2026-10), and without it
only dates on which a series gained a value appear. The answer is
``{"count", "offset", "limit", "release_dates": [{"release_id", "date"}, ...]}``. A release id
FRED does not know answers 200 with an empty list, not an error, so an empty frame is "no such
release (or none in the window)" and the task decides whether that fails its acceptance check.

``start`` / ``end`` of the request bound the real-time period asked for (``realtime_start`` /
``realtime_end``): FRED returns the dates inside it, so ``start`` = 400 days ago and ``end`` =
400 days ahead is the calendar's working window; ``None`` leaves the bound out (all history,
and every scheduled date). The key is not in the URL built here: the registry's transport
appends ``api_key`` (``with_query_param``). One request returns at most ``PAGE_LIMIT`` rows;
``fetch`` pages with ``offset`` until ``count`` is read. A single page is saved as received;
several are saved one document per line, which ``normalize`` reads the same way.

``normalize`` returns ``parsed["release_dates"]`` (``RELEASE_COLUMNS``): ``release_id`` (int),
``release_date`` (``datetime64[ns]``, a calendar day), sorted by date, duplicates dropped.
Point-in-time stamping and the release time of day belong to the task, not here.
"""

import urllib.parse
from typing import NoReturn

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized, TransientFetchError
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.series import RELEASE_FRAME, ReleaseRequest
from algotrade_sources.vendors.fred.observations import BASE_URL, SOURCE, parse_documents

DATASET = "release_dates"
RELEASE_COLUMNS = ("release_id", "release_date")
PAGE_LIMIT = 10_000  # FRED's maximum ``limit`` for release/dates
MAX_PAGES = 20  # a release needing more is a bug, not a release


def release_request(request: FetchRequest) -> ReleaseRequest:
    """``request`` as a ``ReleaseRequest`` (a plain ``FetchRequest`` is the unbounded one)."""
    if isinstance(request, ReleaseRequest):
        return request
    return ReleaseRequest(
        key=request.key, instrument_id=request.instrument_id, session_date=request.session_date
    )


def release_id(request: ReleaseRequest) -> int:
    """The request key as FRED's release id."""
    if not request.key.isdecimal():
        raise ValueError(f"not a FRED release id: {request.key!r}")
    return int(request.key)


def parse_release_dates(payload: bytes) -> pd.DataFrame:
    """``RELEASE_COLUMNS`` rows of every page in ``payload``, sorted by date."""
    records: list[dict[str, object]] = []
    for document in parse_documents(payload):
        if "error_message" in document:
            raise ValueError(f"FRED error: {document['error_message']}")
        if not isinstance(document.get("release_dates"), list):
            raise ValueError("FRED answer has no 'release_dates'")
        records += [
            {"release_id": row["release_id"], "release_date": row["date"]}
            for row in document["release_dates"]
        ]
    frame = pd.DataFrame(records, columns=list(RELEASE_COLUMNS))
    out = pd.DataFrame(
        {
            "release_id": frame["release_id"].astype("int64"),
            "release_date": pd.to_datetime(frame["release_date"]).astype("datetime64[ns]"),
        },
        columns=list(RELEASE_COLUMNS),
    )
    return out.drop_duplicates().sort_values("release_date", kind="stable").reset_index(drop=True)


class FredReleaseDates:
    """Implements ``sources.base.Source``. Request: a ``ReleaseRequest`` (``key`` = the FRED
    release id, ``start`` / ``end`` = the real-time period); the base URL is the source's."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http, base_url: str = BASE_URL, page_limit: int = PAGE_LIMIT) -> None:
        self._http = http  # paced by the shared ``fred`` limiter; adds ``api_key`` itself
        self._base = base_url.rstrip("/")  # ``[fred] base_url`` in sources.toml
        self._limit = page_limit

    def url(self, request: ReleaseRequest, offset: int = 0) -> str:
        """The page's URL, without the key."""
        query: dict[str, str | int] = {
            "release_id": release_id(request),
            "include_release_dates_with_no_data": "true",
            "file_type": "json",
        }
        if request.start is not None:
            query["realtime_start"] = request.start.isoformat()
        if request.end is not None:
            query["realtime_end"] = request.end.isoformat()
        query["limit"], query["offset"] = self._limit, offset
        return f"{self._base}/release/dates?{urllib.parse.urlencode(query)}"

    def fetch(self, request: FetchRequest) -> bytes | None:
        release = release_request(request)
        pages: list[bytes] = []
        for offset in range(0, MAX_PAGES * self._limit, self._limit):
            body = self._http.get(self.url(release, offset))
            if body is None:
                return None if not pages else _gone(release, offset)
            pages.append(body)
            count = parse_documents(body)[0].get("count")
            if not isinstance(count, int):
                raise ValueError(f"FRED release {release.key}: answer has no 'count'")
            if offset + self._limit >= count:
                return pages[0] if len(pages) == 1 else b"\n".join(pages)
        raise ValueError(f"FRED release {release.key}: more than {MAX_PAGES} pages")

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_release_dates(payload)
        return Normalized(session_date=None, tables={}, parsed={RELEASE_FRAME: frame})


def _gone(request: ReleaseRequest, offset: int) -> NoReturn:
    """A page that vanished between pages is not "nothing there"."""
    raise TransientFetchError(f"FRED release {request.key}: page at offset {offset} gone")
