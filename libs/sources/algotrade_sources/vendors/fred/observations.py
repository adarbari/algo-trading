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

FRED refuses a real-time period holding more than 2,000 vintage dates (400 ``exceeds the
maximum number of vintage dates``), which a daily series always does. A request with
``vintages=False`` (an unrevised series, ``pit = "lag"``) leaves the real-time period out: one
plain request for the current values, no vintages. A request with ``vintages=True`` that is
refused is split: the real-time period is halved until FRED accepts each window, the windows'
rows are united, and a span cut at a window edge is joined again (same value, next day), so the
rows are what one request would have returned. The united answer is saved as one document.

``normalize`` returns ``parsed["series"]`` (``SERIES_COLUMNS``): ``series`` is the request key,
``code`` the FRED series id, ``vintage_date`` the row's ``realtime_start``. ``start`` / ``end``
of the request bound the observations asked for (``observation_start`` / ``observation_end``).
"""

import json
import urllib.parse
from datetime import date, timedelta
from typing import Any

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized, TransientFetchError
from algotrade_sources.framework.http import Http, HttpError
from algotrade_sources.framework.pages import json_documents
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
MAX_REQUESTS = 400  # a series needing more windows and pages than this is a bug
MISSING = "."  # FRED's marker for an observation with no value
type Window = tuple[date, date]  # a real-time period, both days included


def missing_series(exc: HttpError) -> bool:
    """FRED answers an unknown series id with 400 and ``series does not exist`` in the body;
    any other 400 (a bad parameter, a bad key) stays an error."""
    return exc.status == 400 and b"series does not exist" in exc.body.lower()


def too_many_vintages(exc: HttpError) -> bool:
    """FRED's 400 for a real-time period with more than 2,000 vintage dates: a refusal of the
    window asked for (``fetch`` halves it), so the transport raises it at once, unretried."""
    return exc.status == 400 and b"maximum number of vintage dates" in exc.body.lower()


def parse_documents(payload: bytes) -> list[dict[str, Any]]:
    """The JSON documents in ``payload`` (one per page, whitespace between)."""
    return json_documents(payload, "FRED")


def halves(window: Window) -> list[Window]:
    """``window`` as its two halves (the second starts the day after the first ends)."""
    first, last = window
    middle = first + (last - first) // 2
    return [(first, middle), (middle + timedelta(days=1), last)]


def join_spans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``rows`` of several real-time windows as one request would have answered: a row repeated
    (same ``date`` and ``realtime_start``) kept once, and the two halves of a span cut at a
    window edge (same value, the second starting the day after the first ends) joined."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        seen.setdefault((row["date"], row["realtime_start"]), row)
    joined: list[dict[str, Any]] = []
    for row in sorted(seen.values(), key=lambda r: (r["date"], r["realtime_start"])):
        last = joined[-1] if joined else None
        if (
            last is not None
            and last["date"] == row["date"]
            and last["value"] == row["value"]
            and _next_day(last["realtime_end"]) == row["realtime_start"]
        ):
            joined[-1] = {**last, "realtime_end": row["realtime_end"]}
        else:
            joined.append(row)
    return joined


def _next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat() if day < LAST_REALTIME else ""


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

    def url(self, request: SeriesRequest, offset: int = 0, window: Window | None = None) -> str:
        """The page's URL, without the key. ``window``: the real-time period; ``None`` leaves it
        out (FRED then answers with the current values)."""
        query: dict[str, str | int] = {"series_id": request.code, "file_type": "json"}
        if window is not None:
            query["realtime_start"], query["realtime_end"] = (d.isoformat() for d in window)
        query["limit"], query["offset"] = self._limit, offset
        if request.start is not None:
            query["observation_start"] = request.start.isoformat()
        if request.end is not None:
            query["observation_end"] = request.end.isoformat()
        return f"{self._base}/series/observations?{urllib.parse.urlencode(query)}"

    def fetch(self, request: FetchRequest) -> bytes | None:
        series = series_request(request)
        if not series.code:
            raise ValueError(f"series {series.key!r}: no FRED series id (code)")
        if not series.vintages:
            return self._pages(series, None)
        full = (date.fromisoformat(FIRST_REALTIME), date.fromisoformat(LAST_REALTIME))
        try:
            return self._pages(series, full)
        except HttpError as exc:
            if not too_many_vintages(exc):
                raise
        return self._windows(series, halves(full))

    def _pages(self, series: SeriesRequest, window: Window | None) -> bytes | None:
        """Every page of one real-time period, as received (several: one document per line);
        ``None`` for an unknown series. Raises the ``HttpError`` of a refused period."""
        pages: list[bytes] = []
        for offset in range(0, MAX_PAGES * self._limit, self._limit):
            body = self._http.get(self.url(series, offset, window))
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

    def _windows(self, series: SeriesRequest, pending: list[Window]) -> bytes:
        """The refused real-time period as the ``pending`` windows, each halved in turn while
        FRED refuses it, their rows united: one document."""
        rows: list[dict[str, Any]] = []
        requests = 0
        while pending:
            window = pending.pop(0)
            requests += 1
            if requests > MAX_REQUESTS:
                raise ValueError(f"FRED {series.code}: more than {MAX_REQUESTS} windows")
            try:
                body = self._pages(series, window)
            except HttpError as exc:
                if not too_many_vintages(exc) or window[0] == window[1]:
                    raise
                pending[:0] = halves(window)
                continue
            if body is None:  # known to exist a moment ago
                raise TransientFetchError(f"FRED {series.code}: window {window[0]} gone")
            for document in parse_documents(body):
                rows.extend(document.get("observations") or [])
        united = join_spans(rows)
        document = {"realtime_start": FIRST_REALTIME, "realtime_end": LAST_REALTIME}
        document |= {"count": len(united), "offset": 0, "limit": len(united)}
        document["observations"] = united
        return json.dumps(document, separators=(",", ":")).encode()

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_observations(series_request(request), payload)
        return Normalized(session_date=None, tables={}, parsed={SERIES_FRAME: frame})
