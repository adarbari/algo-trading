"""The shape every issuer's ETF holdings take before the ingest task stores them.

Issuers publish holdings in their own layouts (State Street workbooks, iShares CSVs, SEC
N-PORT XML). Each adapter under ``vendors/`` reads its own layout and returns the frame built
here, so the ``etf-holdings`` task sees one shape (``HoldingsSource`` in ``base.py``):

- ``weight`` is a fraction of the fund (0.0844 for 8.44%); it can be negative (shorts,
  derivatives, a cash overdraft);
- ``holding_symbol`` is the issuer's ticker for the line in the Nasdaq Trader style
  (``BRK.B``), ``None`` for lines without one (bonds, cash, private lines);
- ``us_listed`` says the issuer's ticker is a U.S. listing, so the task may resolve it to an
  instrument; a foreign line whose local ticker clashes with a U.S. one (Roche ``ROP`` vs
  Roper) stays name-only;
- ``identifier`` is the best security id the issuer gives (CUSIP, else ISIN): a bridge to
  tickers for issuers that publish none (SEC N-PORT).
"""

import re
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

HOLDING_COLUMNS = (
    "holding_symbol",
    "holding_name",
    "weight",
    "asset_class",
    "sector",
    "shares",
    "identifier",
    "us_listed",
)
FUND_COLUMNS = ("symbol", "name")
_TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
_CLASS_SEPARATOR = re.compile(r"^([A-Z]{1,5})[ /-]([A-Z])$")  # "BF B", "BRK/B", "BRK-B"
_NO_VALUE = {"", "-", "--", "nan", "none", "n/a", "unassigned"}


def holding_ticker(raw: object) -> str | None:
    """The issuer's ticker in the universe's style, or ``None`` if the line has no U.S.-style
    ticker (``-``, ``CASH_USD``, ``A000660``, ``ESZ6`` stays: futures are caught by asset class)."""
    text = clean_text(raw)
    if text is None:
        return None
    upper = text.upper()
    match = _CLASS_SEPARATOR.match(upper)
    if match:
        upper = f"{match.group(1)}.{match.group(2)}"
    return upper if _TICKER.match(upper) else None


def clean_text(raw: object) -> str | None:
    """A cell as text; ``None`` for blanks and the placeholders issuers use (``-``, ``nan``)."""
    if raw is None:
        return None
    text = str(raw).strip()
    return None if text.lower() in _NO_VALUE else text


def number(raw: object) -> float | None:
    """A cell as a float: ``"1,234.5"``, ``"9.39%"``, ``"$5"`` and numbers read; else ``None``."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return None if pd.isna(raw) else float(raw)
    text = str(raw).strip().replace(",", "").replace("$", "").rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def fraction(percent: object) -> float:
    """A published percent as a fraction (``"8.44"`` -> 0.0844), 0.0 when it does not read.
    Rounded so float noise from the division never reaches storage."""
    return round((number(percent) or 0.0) / 100, 12)


def holdings_frame(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """The canonical holdings frame (``HOLDING_COLUMNS``) from adapter rows, largest weight
    first (ties keep the issuer's order). Rows without a name or a weight are dropped."""
    frame = pd.DataFrame(list(rows), columns=list(HOLDING_COLUMNS))
    frame = frame[frame["holding_name"].notna() & frame["weight"].notna()]
    frame = frame.astype(
        {"weight": "float64", "shares": "float64", "us_listed": "bool"}, errors="raise"
    )
    return frame.sort_values("weight", ascending=False, kind="stable").reset_index(drop=True)


def funds_frame(rows: Iterable[tuple[str, str]]) -> pd.DataFrame:
    """The directory frame (``FUND_COLUMNS``): one row per published fund ticker."""
    frame = pd.DataFrame(list(rows), columns=list(FUND_COLUMNS))
    return frame.drop_duplicates("symbol").sort_values("symbol").reset_index(drop=True)
