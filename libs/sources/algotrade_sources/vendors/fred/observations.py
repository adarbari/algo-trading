"""FRED / ALFRED ``series/observations``: one economic series with every vintage (ADR 0048).

``GET <base_url>/series/observations?series_id=<id>&file_type=json&realtime_start=1776-07-04
&realtime_end=9999-12-31&limit=100000&offset=<n>&api_key=<key>`` (free key, see
docs/data/vendors.md). Asking for the full real-time period returns one row per observation
and per span in which its value stood: ``{"realtime_start", "realtime_end", "date", "value"}``,
so a revised observation appears once for each value it has had, and ``realtime_start`` is the
day that value became known (ALFRED's "vintage"). FRED writes a missing observation as ``"."``;
it becomes a null value, not a dropped row.

The key is not in the URL this module builds: the registry's transport appends ``api_key``
(``with_query_param``), so it never reaches a log line or an error message. An unknown series
answers 400 with ``"... series does not exist"``: ``fetch`` -> ``None`` (``missing_series``).

One request returns at most ``PAGE_LIMIT`` rows; ``fetch`` pages with ``offset`` until
``count`` is read. A single page is saved as received; several are saved as their JSON
documents one after another (one per line), which ``normalize`` reads the same way.

``normalize`` returns ``parsed["series"]`` (``SERIES_COLUMNS``): ``series`` is the request key,
``code`` the FRED series id, ``vintage_date`` the row's ``realtime_start``. ``start`` / ``end``
of the request bound the observations asked for (``observation_start`` / ``observation_end``).
"""

import json
import urllib.parse
from typing import Any

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized, TransientFetchError
from algotrade_sources.framework.http import Http, HttpError
from algotrade_sources.framework.series import (
    SERIES_FRAME,
    SeriesRequest,
    normalise_series_frame,
    series_request,
)

SOURCE = "fred"
DATASET = "observations"
BASE_URL = "https://api.stlouisfed.org/fred"
FIRST_REALTIME = "1776-07-04"  # FRED's earliest real-time date
LAST_REALTIME = "9999-12-31"  # FRED's "until revised"
PAGE_LIMIT = 100_000  # FRED's maximum ``limit``
MAX_PAGES = 50  # a series needing more is a bug, not a series
MISSING = "."  # FRED's marker for an observation with no value


def missing_series(exc: HttpError) -> bool:
    """FRED answers an unknown series id with 400 and ``series does not exist`` in the body;
    any other 400 (a bad parameter, a bad key) stays an error."""
    return exc.status == 400 and b"series does not exist" in exc.body.lower()


def parse_documents(payload: bytes) -> list[dict[str, Any]]:
    """The JSON documents in ``payload`` (one per page, whitespace between)."""
    text, decoder, pos, documents = payload.decode("utf-8-sig"), json.JSONDecoder(), 0, []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        try:
            document, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError as exc:
            raise ValueError(f"FRED answer is not JSON: {exc}") from exc
        if not isinstance(document, dict):
            raise ValueError("FRED answer is not a JSON object")
        documents.append(document)
    if not documents:
        raise ValueError("FRED answer is empty")
    return documents


def parse_observations(request: SeriesRequest, payload: bytes) -> pd.DataFrame:
    """``SERIES_COLUMNS`` rows of every page in ``payload``."""
    records = []
    for document in parse_documents(payload):
        if "error_message" in document:
            raise ValueError(f"FRED error: {document['error_message']}")
        if not isinstance(document.get("observations"), list):
            raise ValueError("FRED answer has no 'observations'")
        for row in document["observations"]:
            value = row["value"]
            records.append(
                {
                    "series": request.key,
                    "obs_date": row["date"],
                    "vintage_date": row["realtime_start"],
                    "value": None if value == MISSING else value,
                    "code": request.code,
                }
            )
    columns = ["series", "obs_date", "vintage_date", "value", "code"]
    return normalise_series_frame(pd.DataFrame(records, columns=columns))


class FredObservations:
    """Implements ``sources.base.Source``. Request: a ``SeriesRequest`` (``key``, ``code`` =
    the FRED series id, ``start`` / ``end``); the base URL is the source's, not the request's."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http, base_url: str = BASE_URL, page_limit: int = PAGE_LIMIT) -> None:
        self._http = http  # paced by the shared ``fred`` limiter; adds ``api_key`` itself
        self._base = base_url.rstrip("/")  # ``[fred] base_url`` in sources.toml
        self._limit = page_limit

    def url(self, request: SeriesRequest, offset: int = 0) -> str:
        """The page's URL, without the key."""
        query = {
            "series_id": request.code,
            "file_type": "json",
            "realtime_start": FIRST_REALTIME,
            "realtime_end": LAST_REALTIME,
            "limit": self._limit,
            "offset": offset,
        }
        if request.start is not None:
            query["observation_start"] = request.start.isoformat()
        if request.end is not None:
            query["observation_end"] = request.end.isoformat()
        return f"{self._base}/series/observations?{urllib.parse.urlencode(query)}"

    def fetch(self, request: FetchRequest) -> bytes | None:
        series = series_request(request)
        if not series.code:
            raise ValueError(f"series {series.key!r}: no FRED series id (code)")
        pages: list[bytes] = []
        for offset in range(0, MAX_PAGES * self._limit, self._limit):
            body = self._http.get(self.url(series, offset))
            if body is None:
                if pages:  # the series vanished between pages: not "nothing there"
                    raise TransientFetchError(f"FRED {series.code}: page at offset {offset} gone")
                return None
            pages.append(body)
            count = parse_documents(body)[0].get("count")
            if not isinstance(count, int):
                raise ValueError(f"FRED {series.code}: answer has no 'count'")
            if offset + self._limit >= count:
                return pages[0] if len(pages) == 1 else b"\n".join(pages)
        raise ValueError(f"FRED {series.code}: more than {MAX_PAGES} pages")

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_observations(series_request(request), payload)
        return Normalized(session_date=None, tables={}, parsed={SERIES_FRAME: frame})
