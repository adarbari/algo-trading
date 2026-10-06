"""The shape every economic-series adapter returns, and the request that asks for one (ADR 0048).

FRED / ALFRED observations and published files (Stooq, the Fed's EBP, OFR FSI, Shiller) speak
different formats; each adapter reads its own and returns the frame built here, so the ``macro``
ingestion task sees one shape (``parsed["series"]`` of ``Normalized``, ``SERIES_FRAME``):

- ``series`` is the registry key (``config/site/macro.toml``), ``code`` the vendor's own code
  (the FRED series id; a published file's column name);
- ``obs_date`` is the day the value describes, ``vintage_date`` the day that value became
  known. ALFRED rows carry ``realtime_start`` there (one row per value change); a published
  file has no vintages, so it is ``NaT`` and the ``lagged`` rule (``obs_date`` + release lag)
  is applied downstream, not here;
- ``value`` is a float; ``NaN`` where the vendor publishes a missing observation (FRED's
  ``"."``);
- dates are midnight ``datetime64[ns]`` (calendar days, not instants); storage casts them to
  ``date``. Point-in-time stamping (``knowledge_ts`` etc.) belongs to the task, not here.

``SeriesRequest`` is a ``FetchRequest`` plus what the registry knows about the series; the task
builds it from the registry, so adapters hold no per-series knowledge.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade_sources.framework.base import FetchRequest

SERIES_FRAME = "series"  # key of ``Normalized.parsed`` holding the normalised frame
SERIES_COLUMNS = ("series", "obs_date", "vintage_date", "value", "code")


@dataclass(frozen=True, kw_only=True)
class SeriesRequest(FetchRequest):
    """One series to fetch. ``key`` is the registry key.

    ``code``: the vendor's code (the FRED series id). ``url``, ``date_column``,
    ``value_column`` and ``parser`` describe a published file (``vendors/published/
    parsers.py``). ``start`` / ``end`` bound ``obs_date`` (inclusive; ``None``: unbounded)."""

    code: str = ""
    url: str = ""
    date_column: str = "date"
    value_column: str = "value"
    parser: str = "csv"
    start: date | None = None
    end: date | None = None


def series_request(request: FetchRequest) -> SeriesRequest:
    """``request`` as a ``SeriesRequest`` (adapters take no other kind)."""
    if not isinstance(request, SeriesRequest):
        raise TypeError(f"a series source needs a SeriesRequest, got {type(request).__name__}")
    return request


def normalise_series_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """``frame`` with exactly ``SERIES_COLUMNS``: dtypes enforced, rows sorted by
    (``series``, ``obs_date``, ``vintage_date``), exact duplicates dropped."""
    out = pd.DataFrame(
        {
            "series": frame["series"].astype(str),
            "obs_date": pd.to_datetime(frame["obs_date"]).astype("datetime64[ns]"),
            "vintage_date": pd.to_datetime(frame["vintage_date"]).astype("datetime64[ns]"),
            "value": pd.to_numeric(frame["value"], errors="coerce").astype("float64"),
            "code": frame["code"].astype(str),
        },
        columns=list(SERIES_COLUMNS),
    )
    out = out.sort_values(["series", "obs_date", "vintage_date"], kind="stable")
    return out.drop_duplicates().reset_index(drop=True)
