"""Parse the vendor's one-off ``stockhistory`` files (ADR 0086): ``dividends.csv`` (symbol,
ex-date, amount) and ``stocksplits.csv`` (symbol, date, ratio, text), both headerless, dates
``M/D/YYYY``. Stored as the vendor's facts and compared with ``events/dividend`` and
``events/split``; never merged into them."""

from typing import IO

import pandas as pd


def parse_dividends(stream: IO[bytes]) -> pd.DataFrame:
    """-> ``symbol, ex_date, amount``."""
    raw = pd.read_csv(stream, header=None, names=["symbol", "ex_date", "amount"], dtype=str)
    out = pd.DataFrame(
        {
            "symbol": raw["symbol"].str.strip().str.upper(),
            "ex_date": pd.to_datetime(raw["ex_date"], format="%m/%d/%Y").dt.date,
            "amount": pd.to_numeric(raw["amount"], errors="coerce"),
        }
    )
    return out.dropna(subset=["amount"]).reset_index(drop=True)


def parse_splits(stream: IO[bytes]) -> pd.DataFrame:
    """-> ``symbol, ex_date, ratio, text``: ``ratio`` is new shares per old (``3 for 2`` is 1.5,
    ``1 for 3`` is 0.3333), ``text`` the vendor's words."""
    raw = pd.read_csv(stream, header=None, names=["symbol", "ex_date", "ratio", "text"], dtype=str)
    out = pd.DataFrame(
        {
            "symbol": raw["symbol"].str.strip().str.upper(),
            "ex_date": pd.to_datetime(raw["ex_date"], format="%m/%d/%Y").dt.date,
            "ratio": pd.to_numeric(raw["ratio"], errors="coerce"),
            "text": raw["text"].str.strip(),
        }
    )
    return out.dropna(subset=["ratio"]).reset_index(drop=True)
