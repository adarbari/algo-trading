"""A published dated table as an economic series (ADR 0048), driven by the registry entry.

The file at the request's ``url`` is read by the named ``parser`` (``parsers.py``) into a
table; ``date_column`` and ``value_column`` pick the observation date and the value. Nothing
about a particular file lives here, so one more CSV is a ``config/site/macro.toml`` entry.

A published file has no vintages: ``vintage_date`` is null and the registry's release lag
(the ``lagged`` rule) is applied downstream. The whole file is read each time (raw saved as
received); the request's ``start`` / ``end`` bound the rows ``normalize`` returns. A cell that
does not read as a number is a null value; a row whose date does not read is dropped. A body
that is not the expected table (an HTML page such as a browser-verification challenge, nothing
at all, or a table without the requested columns) raises ``TransientFetchError`` with the
first ``PREVIEW`` characters of the body, so the task records a ``FETCH_ERROR`` and never a
silent empty series.
"""

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized, TransientFetchError
from algotrade_sources.framework.http import Http
from algotrade_sources.framework.series import (
    SERIES_FRAME,
    SeriesRequest,
    normalise_series_frame,
    series_request,
)
from algotrade_sources.vendors.published.parsers import PARSERS

SOURCE = "published"
DATASET = "series_file"
SCHEMES = ("https://", "http://")
PREVIEW = 80  # characters of a refused body quoted in the error


def _refused(request: SeriesRequest, payload: bytes, why: str) -> TransientFetchError:
    head = payload.decode("utf-8", errors="replace").strip()[:PREVIEW]
    return TransientFetchError(f"series {request.key!r}: {why}; the body starts {head!r}")


def parse_series(request: SeriesRequest, payload: bytes) -> pd.DataFrame:
    """``SERIES_COLUMNS`` rows of the file, bounded by the request's ``start`` / ``end``."""
    parser = PARSERS.get(request.parser)
    if parser is None:
        raise ValueError(f"series {request.key!r}: unknown parser {request.parser!r}")
    if not payload.strip():
        raise _refused(request, payload, "the file is empty")
    if payload.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        raise _refused(request, payload, "an HTML page, not the table")
    table = parser(payload)
    missing = [c for c in (request.date_column, request.value_column) if c not in table.columns]
    if missing:
        raise _refused(
            request,
            payload,
            f"no column {missing} in the file (has {[str(c) for c in table.columns][:8]})",
        )
    dates = pd.to_datetime(table[request.date_column], errors="coerce")
    frame = _rows(request, dates, table[request.value_column])
    frame = frame[frame["obs_date"].notna()]
    if request.start is not None:
        frame = frame[frame["obs_date"] >= pd.Timestamp(request.start)]
    if request.end is not None:
        frame = frame[frame["obs_date"] <= pd.Timestamp(request.end)]
    return normalise_series_frame(frame)


def _rows(request: SeriesRequest, dates: object, values: object) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "series": request.key,
            "obs_date": dates,
            "vintage_date": pd.NaT,
            "value": values,
            "code": request.code or request.value_column,
        },
        columns=["series", "obs_date", "vintage_date", "value", "code"],
    )


class PublishedSeries:
    """Implements ``sources.base.Source``. Request: a ``SeriesRequest`` (``key``, ``url``,
    ``date_column``, ``value_column``, ``parser``, ``start`` / ``end``)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``published`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        series = series_request(request)
        if not series.url.startswith(SCHEMES):
            raise ValueError(f"series {series.key!r}: url must be http(s), got {series.url!r}")
        body = self._http.get(series.url)
        return body if body is not None and body.strip() else None  # an empty file: nothing yet

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        frame = parse_series(series_request(request), payload)
        return Normalized(session_date=None, tables={}, parsed={SERIES_FRAME: frame})
