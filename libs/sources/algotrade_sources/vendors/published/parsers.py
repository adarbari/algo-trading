"""Named parsers for published series files: bytes -> a table of text cells with a header.

``PARSERS`` maps the registry's ``parser`` name to a function; ``csv_series.PublishedSeries``
then picks the request's ``date_column`` and ``value_column`` from the table, so a file in a
plain format needs no code, only a registry entry:

- ``csv``: a comma-separated file with a header row. Stooq daily
  (``Date,Open,High,Low,Close,Volume``, ``value_column = "Close"``), the Fed's EBP
  (``ebp_csv.csv``: ``date,gz_spread,ebp,est_prob``, monthly) and the OFR financial stress
  index (``fsi.csv``: ``Date,OFR FSI,Credit,...``, daily) all read this way;
- ``epu_daily``: the daily Economic Policy Uncertainty CSV (``All_Daily_Policy_Data.csv``:
  ``day,month,year,daily_policy_index``): the date is in three columns, so this parser adds a
  ``date`` column (ISO ``YYYY-MM-DD``; a row whose parts do not form a date gets none);
- ``shiller_xls``: Shiller's ``ie_data.xls`` (a legacy Excel workbook with a multi-row header).
  Reading ``.xls`` needs ``xlrd``, which is not a dependency (``openpyxl``, the one workbook
  reader we ship, reads only ``.xlsx``), so it raises ``NotImplementedError`` until that
  dependency is added in its own PR (follow-up in docs/data/vendors.md).

An empty body is an empty table (a file with nothing in it yet), not an error.
"""

import io
from collections.abc import Callable

import pandas as pd

type Parser = Callable[[bytes], pd.DataFrame]


def parse_csv(payload: bytes) -> pd.DataFrame:
    """A CSV with a header row, every cell kept as text (the caller types the two it uses)."""
    if not payload.strip():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(io.BytesIO(payload), dtype=str, encoding="utf-8-sig")
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValueError(f"not a CSV table: {exc}") from exc
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


EPU_PARTS = ("year", "month", "day")


def parse_epu_daily(payload: bytes) -> pd.DataFrame:
    """The daily EPU CSV with a ``date`` column built from ``year``, ``month`` and ``day``."""
    frame = parse_csv(payload)
    if frame.empty and not len(frame.columns):
        return frame
    missing = [c for c in EPU_PARTS if c not in frame.columns]
    if missing:
        raise ValueError(f"not the daily EPU file: no column {missing}")
    parts = frame[list(EPU_PARTS)].apply(pd.to_numeric, errors="coerce")
    dates = pd.to_datetime(parts, errors="coerce")
    frame["date"] = dates.dt.strftime("%Y-%m-%d").where(dates.notna(), None)
    return frame


def parse_shiller_xls(payload: bytes) -> pd.DataFrame:
    """Shiller's ``ie_data.xls``: not readable until ``xlrd`` is a dependency."""
    raise NotImplementedError(
        "shiller_xls needs an .xls reader (xlrd), which is not a dependency yet: "
        "add it to apps/ingestion's pyproject in its own PR"
    )


PARSERS: dict[str, Parser] = {
    "csv": parse_csv,
    "epu_daily": parse_epu_daily,
    "shiller_xls": parse_shiller_xls,
}
