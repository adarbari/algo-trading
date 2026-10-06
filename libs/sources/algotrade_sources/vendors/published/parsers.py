"""Named parsers for published series files: bytes -> a table of text cells with a header.

``PARSERS`` maps the registry's ``parser`` name to a function; ``csv_series.PublishedSeries``
then picks the request's ``date_column`` and ``value_column`` from the table, so a file in a
plain format needs no code, only a registry entry:

- ``csv``: a comma-separated file with a header row. Stooq daily
  (``Date,Open,High,Low,Close,Volume``, ``value_column = "Close"``), the Fed's EBP
  (``ebp_csv.csv``: ``date,gz_spread,ebp,est_prob``, monthly) and the OFR financial stress
  index (daily CSV, one column per index) all read this way;
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


def parse_shiller_xls(payload: bytes) -> pd.DataFrame:
    """Shiller's ``ie_data.xls``: not readable until ``xlrd`` is a dependency."""
    raise NotImplementedError(
        "shiller_xls needs an .xls reader (xlrd), which is not a dependency yet: "
        "add it to apps/ingestion's pyproject in its own PR"
    )


PARSERS: dict[str, Parser] = {"csv": parse_csv, "shiller_xls": parse_shiller_xls}
