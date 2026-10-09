"""S&P 500 membership intervals (``Sp500Membership``; edges ED6b-3, ADR 0013 over history).

``sp500_ticker_start_end.csv`` of https://github.com/fja05680/sp500 (MIT licence, by fja05680,
rebuilt from S&P's change announcements and Wikipedia): one row per membership interval,
``ticker, start_date, end_date``; ``end_date`` is blank while the ticker is a member, and a
ticker that left and came back has one row per stay (``AAL``). The tickers are the ones used
at the time (``FB`` until 2022-06-09, ``META`` since), so a row says "the listing trading under
this ticker was a member", which ``data.listings.universe_asof`` joins to the listing alive on
the day. The project's daily-snapshot file (``sp500_components_updated.csv``, 5.5 MB) holds the
same history day by day and is not read: this file is the one 28 KB request.

The project writes a share class with a dot (``BRK.B``, ``BF.B``); Tiingo and the listing
history write it with a hyphen (``BRK-B``), so the dot becomes a hyphen here.

Reliable from about 2001 (the project says so); earlier rows are kept as published. Rows with
no ticker or an unparseable ``start_date`` are dropped and counted in ``Normalized.notes``.
"""

import io

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http

SOURCE = "sp500_history"
DATASET = "membership"
TABLE = "instruments/index_membership"
INDEX = "SP500"
URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
HEADER = ("ticker", "start_date", "end_date")
COLUMNS = ["index_name", "ticker", "start_date", "end_date"]


def parse_membership(payload: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """The CSV -> (``COLUMNS`` rows, rows dropped by reason)."""
    raw = pd.read_csv(io.BytesIO(payload), dtype=str, keep_default_na=False)
    missing = [c for c in HEADER if c not in raw.columns]
    if missing:
        raise ValueError(f"S&P 500 membership CSV lacks columns {missing}")
    ticker = raw["ticker"].str.strip().str.upper().str.replace(".", "-", regex=False)
    start = pd.to_datetime(raw["start_date"].str.strip(), errors="coerce")
    end = pd.to_datetime(raw["end_date"].str.strip(), errors="coerce")
    no_ticker, no_start = ticker == "", start.isna()
    drop = no_ticker | no_start
    rows = pd.DataFrame(
        {
            "index_name": INDEX,
            "ticker": ticker,
            "start_date": start.dt.date,
            "end_date": end.dt.date.where(end.notna(), None),
        }
    )[~drop]
    rows = rows.drop_duplicates(["ticker", "start_date"], keep="last")
    dropped = {
        "no_ticker": int(no_ticker.sum()),
        "no_start_date": int((no_start & ~no_ticker).sum()),
    }
    return rows.sort_values(["ticker", "start_date"]).reset_index(drop=True)[COLUMNS], dropped


class Sp500Membership:
    """Implements ``sources.base.Source``. The request key is ignored (one file)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the ``sp500_history`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(URL)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        rows, dropped = parse_membership(payload)
        return Normalized(
            session_date=request.session_date,
            tables={},
            notes={f"dropped_{k}": v for k, v in dropped.items()},
            parsed={TABLE: rows},
        )
