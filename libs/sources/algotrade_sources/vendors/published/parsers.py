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
- ``cape_csv``: Barclays' Shiller CAPE file (``cape.csv``: ``Date`` as ``dd/mm/yyyy`` month-ends,
  then one column per country). The date is read day first (a plain ``csv`` read would take
  ``05/10/1982`` as May) and written ISO; ``0`` (before a country's start) and ``#VALUE!``
  are no value, as a blank cell;
- ``french_zip``: a file of Kenneth French's data library (a zip holding one CSV, CRLF lines, a
  free-text preamble, then one or more sections: a header line that starts with a comma, rows of
  ``YYYYMMDD`` and percent returns, a blank line; a copyright footer after the last one). A
  section is found by its header line (the preamble has blank lines too), counted from 1 as the
  registry's ``section`` (the industry files hold the value-weighted section, then the
  equal-weighted one). The empty first header cell is named ``date``, column names lose their
  padding (``Mom   ``), the date is written ISO, and ``-99.99`` / ``-999`` (the library's missing
  marks) are no value. Values stay in percent, as published;
- ``shiller_xls``: Shiller's ``ie_data.xls`` (a legacy Excel workbook with a multi-row header).
  Reading ``.xls`` needs ``xlrd``, which is not a dependency (``openpyxl``, the one workbook
  reader we ship, reads only ``.xlsx``), so it raises ``NotImplementedError`` until that
  dependency is added in its own PR (follow-up in docs/data/vendors.md).

An empty body is an empty table (a file with nothing in it yet), not an error.
"""

import io
import zipfile
from collections.abc import Callable
from functools import lru_cache

import pandas as pd

type Parser = Callable[..., pd.DataFrame]


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


BARCLAYS_NO_VALUE = {"0", "0.0", "0.00", "#VALUE!", "#N/A", "N/A", "NA"}


def parse_cape_csv(payload: bytes) -> pd.DataFrame:
    """Barclays' ``cape.csv``: ISO ``Date`` (a row whose date does not read gets none) and every
    country column as text, with the file's ``0`` / ``#VALUE!`` placeholders blanked."""
    frame = parse_csv(payload)
    if "Date" not in frame.columns:
        return frame
    dates = pd.to_datetime(frame["Date"].str.strip(), format="%d/%m/%Y", errors="coerce")
    frame["Date"] = dates.dt.strftime("%Y-%m-%d").where(dates.notna(), None)
    for column in frame.columns.drop("Date"):
        cells = frame[column].str.strip()
        frame[column] = cells.where(~cells.isin(BARCLAYS_NO_VALUE), None)
    return frame


FRENCH_NO_VALUE = ("-99.99", "-999")  # the library's missing marks, as published
FRENCH_SECTIONS_CACHED = 2  # a file's series are consecutive, so one section is parsed once


def _french_text(payload: bytes) -> list[str]:
    """The lines of the one CSV inside the zip."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if len(names) != 1:
                raise ValueError(f"expected one CSV in the zip, found {archive.namelist()}")
            raw = archive.read(names[0])
    except zipfile.BadZipFile as exc:
        raise ValueError(f"not a zip file: {exc}") from exc
    return raw.decode("utf-8-sig", errors="replace").splitlines()


@lru_cache(maxsize=FRENCH_SECTIONS_CACHED)
def _french_section(payload: bytes, section: int) -> pd.DataFrame:
    lines = _french_text(payload)
    headers = [i for i, line in enumerate(lines) if line.startswith(",")]
    if section < 1 or section > len(headers):
        raise ValueError(f"no section {section} in the file ({len(headers)} found)")
    start = headers[section - 1]
    end = next((i for i in range(start + 1, len(lines)) if not lines[i].strip()), len(lines))
    frame = parse_csv("\n".join(lines[start:end]).encode())
    frame = frame.rename(columns={frame.columns[0]: "date"})
    dates = pd.to_datetime(frame["date"].str.strip(), format="%Y%m%d", errors="coerce")
    frame["date"] = dates.dt.strftime("%Y-%m-%d").where(dates.notna(), None)
    for column in frame.columns.drop("date"):
        cells = frame[column].str.strip()
        frame[column] = cells.where(~cells.isin(FRENCH_NO_VALUE), None)
    return frame


def parse_french_zip(payload: bytes, section: int = 1) -> pd.DataFrame:
    """One section of a French data-library zip (the module docstring says how it is found)."""
    return _french_section(payload, section).copy()  # the cached table is shared: never hand it out


SECTIONED = frozenset({"french_zip"})  # parsers that take the registry's ``section``


def parse_shiller_xls(payload: bytes) -> pd.DataFrame:
    """Shiller's ``ie_data.xls``: not readable until ``xlrd`` is a dependency."""
    raise NotImplementedError(
        "shiller_xls needs an .xls reader (xlrd), which is not a dependency yet: "
        "add it to apps/ingestion's pyproject in its own PR"
    )


PARSERS: dict[str, Parser] = {
    "csv": parse_csv,
    "epu_daily": parse_epu_daily,
    "cape_csv": parse_cape_csv,
    "french_zip": parse_french_zip,
    "shiller_xls": parse_shiller_xls,
}
