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
builds it from the registry, so adapters hold no per-series knowledge. ``ReleaseRequest`` asks
the release-dates source (FRED ``release/dates``, ADR 0050) for one release, bounded in real
time; its answer is ``parsed[RELEASE_FRAME]`` (``vendors/fred/releases.py``). ``FilingsRequest``
asks the SEC filings source for one company's 8-Ks (ADR 0050); its answer is
``parsed[FILINGS_FRAME]`` with ``FILING_COLUMNS`` (``vendors/sec/submissions.py``).
``DailyIndexRequest`` asks the SEC daily form index for one filing day: which CIKs filed an
8-K that day, ``parsed[DAILY_INDEX_FRAME]`` with ``DAILY_INDEX_COLUMNS``
(``vendors/sec/daily_index.py``). They live here so a task builds its requests without
importing a vendor module.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade_sources.framework.base import FetchRequest

SERIES_FRAME = "series"  # key of ``Normalized.parsed`` holding the normalised frame
SERIES_COLUMNS = ("series", "obs_date", "vintage_date", "value", "code")
RELEASE_FRAME = "release_dates"  # key of ``Normalized.parsed`` holding a release's dates (ADR 0050)
FILINGS_FRAME = "filings"  # key of ``Normalized.parsed`` holding a company's 8-K rows (ADR 0050)
DAILY_INDEX_FRAME = "daily_index"  # key of ``Normalized.parsed`` holding a day's 8-K filers
DAILY_INDEX_COLUMNS = ("cik", "form", "accession", "filing_date")
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
    vintages: bool = True  # FRED: every vintage (ALFRED); False: the current values only
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True, kw_only=True)
class ReleaseRequest(FetchRequest):
    """One FRED release. ``key`` is the release id (digits, e.g. ``"10"`` for the CPI);
    ``start`` / ``end`` bound the real-time period (inclusive; ``None``: unbounded)."""

    start: date | None = None
    end: date | None = None


@dataclass(frozen=True, kw_only=True)
class FilingsRequest(FetchRequest):
    """One company's filings. ``key`` is the CIK (digits); ``since``: the earliest filing date
    wanted (``None``: the recent block only)."""

    since: date | None = None


@dataclass(frozen=True, kw_only=True)
class DailyIndexRequest(FetchRequest):
    """One filing day of the SEC daily form index (``key`` is the day, ISO); ``day`` is the
    date SEC filed under (a filing accepted after 17:30 New York time is dated the next business
    day)."""

    day: date


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
