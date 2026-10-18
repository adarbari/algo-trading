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
(``vendors/sec/daily_index.py``). ``ProspectusSearchRequest`` asks EDGAR full-text search for
the 424B4 final prospectuses mentioning a lock-up filed in a window, ``parsed[HITS_FRAME]`` with
``HIT_COLUMNS`` (``vendors/sec/prospectus_search.py``); ``ProspectusRequest`` asks for one
prospectus's main document, ``parsed[IPO_FRAME]`` with the IPO facts read from its text
(``vendors/sec/prospectus.py``). They live here so a task builds its requests without importing a
vendor module.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade_sources.framework.base import FetchRequest

SERIES_FRAME = "series"  # key of ``Normalized.parsed`` holding the normalised frame
SERIES_COLUMNS = ("series", "obs_date", "vintage_date", "value", "code")
RELEASE_FRAME = "release_dates"  # key of ``Normalized.parsed`` holding a release's dates (ADR 0050)
# The SEC event forms kept (ADR 0050): 8-K and 8-K/A (with items; Item 2.02 rows are results
# releases), late-filing notices (12b-25), the issuer's own tender offer (its amendments SC TO-I/A
# are left out), delisting notices (25 by the issuer, 25-NSE by the exchange: also filed for a
# bond or a preferred), final prospectuses and Form 10 registrations of a class. Amendments of the
# new forms are not kept: the original carries the event.
FILING_FORMS = ("8-K", "8-K/A", "NT 10-K", "NT 10-Q", "SC TO-I", "25", "25-NSE", "424B4", "10-12B")
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


HITS_FRAME = "prospectus_hits"  # key of ``Normalized.parsed`` holding a window's 424B4 hits
HIT_COLUMNS = ("cik", "accession", "filing_date", "name")
IPO_FRAME = "ipo_facts"  # key of ``Normalized.parsed`` holding one prospectus's IPO facts (one row)
IPO_RULES_VERSION = "v1"  # bump with any extraction rule: the task re-reads rows of an older one
IPO_EXTRACTED = "EXTRACTED"  # the ``extraction`` status that carries a lock-up term
IPO_COLUMNS = (
    "is_ipo",
    "prospectus_date",
    "ticker",
    "exchange",
    "offer_price",
    "lockup_n",
    "lockup_unit",
    "lockup_terms",
    "early_release",
    "early_release_text",
    "extraction",
    "reason",
)


@dataclass(frozen=True, kw_only=True)
class DailyIndexRequest(FetchRequest):
    """One filing day of the SEC daily form index (``key`` is the day, ISO); ``day`` is the
    date SEC filed under (a filing accepted after 17:30 New York time is dated the next business
    day)."""

    day: date


@dataclass(frozen=True, kw_only=True)
class ProspectusSearchRequest(FetchRequest):
    """424B4 filings that mention a lock-up, filed from ``start`` through ``end`` (inclusive
    calendar days; ``key`` is ``start..end``, ISO)."""

    start: date
    end: date


@dataclass(frozen=True, kw_only=True)
class ProspectusRequest(FetchRequest):
    """One 424B4: ``key`` is its accession number, ``cik`` the filer's (digits), ``document`` the
    main document's file name as the submissions list it (empty for an old filing that lists none:
    the whole submission text is read instead)."""

    cik: str
    document: str = ""


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
