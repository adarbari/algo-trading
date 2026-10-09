"""Tiingo's supported-tickers file: every ticker it ever listed with its dates
(``TiingoSupportedTickers``; the listing history behind the winners study, ADR 0018
amendment 2026-10-08, edges ED6).

``https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip`` is one public ZIP with
one CSV, ``supported_tickers.csv``: ``ticker, exchange, assetType, priceCurrency, startDate,
endDate``. ``startDate`` / ``endDate`` are the first and last day Tiingo has prices for the
ticker; ``endDate`` of a live name is a recent day, and blank when Tiingo has no prices. It
has no ``permaTicker`` (that comes from the per-ticker meta endpoint, a later adapter), so
``perma_ticker`` is empty here and the task decides ids.

Kept: USD, the exchanges ``EXCHANGES`` (Tiingo's ``NYSE MKT`` / ``NYSE ARCA`` are our
``AMEX`` / ``ARCA``), asset type Stock or ETF, a plain ticker (``TICKER``: share classes ``BRK-B``
are kept; the file also lists preferreds, units, notes and expiring warrants under tickers such
as ``BC/PA``, ``CFX 5.75`` or ``CAPTW(EXP20260807)``, which are not names we trade) and a
parseable ``startDate``. The rest is counted in ``Normalized.notes``. Recorded 2026-10-08
(108,972 rows, 24,550 of them kept at the first pull; a live name's ``endDate`` is the file's
latest day). The file is one request, so the shared ``tiingo`` limiter is not a
constraint.
"""

import io
import re
import zipfile
from collections.abc import Mapping
from datetime import date

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http

SOURCE = "tiingo"
DATASET = "supported_tickers"
TABLE = "instruments/listing_history"
URL = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
CSV_NAME = "supported_tickers.csv"
HEADER = ("ticker", "exchange", "assetType", "priceCurrency", "startDate", "endDate")
EXCHANGES: Mapping[str, str] = {
    "NYSE": "NYSE",
    "NASDAQ": "NASDAQ",
    "AMEX": "AMEX",
    "NYSE MKT": "AMEX",
    "ARCA": "ARCA",
    "NYSE ARCA": "ARCA",
    "BATS": "BATS",
}
ASSET_TYPES = {"STOCK": "Stock", "ETF": "ETF"}
TICKER = re.compile(r"[A-Z0-9]+(?:[.-][A-Z0-9]+)*")
COLUMNS = [
    "ticker",
    "exchange",
    "asset_type",
    "price_currency",
    "start_date",
    "end_date",
    "perma_ticker",
]


def parse_listings(payload: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """The ZIP (or the bare CSV) -> (``COLUMNS`` rows kept, rows dropped by reason)."""
    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise ValueError("supported tickers ZIP holds no CSV")
            payload = archive.read(CSV_NAME if CSV_NAME in names else names[0])
    raw = pd.read_csv(io.BytesIO(payload), dtype=str, keep_default_na=False)
    missing = [c for c in HEADER if c not in raw.columns]
    if missing:
        raise ValueError(f"supported tickers CSV lacks columns {missing}")
    ticker = raw["ticker"].str.strip().str.upper()
    exchange = raw["exchange"].str.strip().str.upper().map(EXCHANGES)
    asset = raw["assetType"].str.strip().str.upper().map(ASSET_TYPES)
    currency = raw["priceCurrency"].str.strip().str.upper()
    start = pd.to_datetime(raw["startDate"].str.strip(), errors="coerce")
    end = pd.to_datetime(raw["endDate"].str.strip(), errors="coerce")
    end = end.where(end != end.max())  # the file's latest day: still listed (open)
    reasons = {
        "not_usd": currency != "USD",
        "other_exchange": exchange.isna(),
        "other_asset_type": asset.isna(),
        "no_start_date": start.isna(),
        "no_ticker": ticker == "",
        "odd_ticker": (ticker != "") & ~ticker.str.fullmatch(TICKER),
    }
    drop = pd.Series(False, index=raw.index)
    dropped: dict[str, int] = {}
    for reason, mask in reasons.items():  # each row counted under its first reason
        dropped[reason] = int((mask & ~drop).sum())
        drop |= mask
    kept = pd.DataFrame(
        {
            "ticker": ticker,
            "exchange": exchange,
            "asset_type": asset,
            "price_currency": currency,
            "start_date": start.dt.date,
            "end_date": end.dt.date.where(end.notna(), None),
            "perma_ticker": "",
        }
    )[~drop]
    # The file lists a few (ticker, startDate) twice (a Stock and an ETF row, a re-listing on its
    # first day): keep the row that is still open, else the one that lasted longest.
    kept = kept.assign(_last=kept["end_date"].fillna(date.max))
    kept = kept.sort_values(["ticker", "start_date", "_last"], kind="stable")
    kept = kept.drop_duplicates(["ticker", "start_date"], keep="last").drop(columns="_last")
    return kept.reset_index(drop=True)[COLUMNS], dropped


class TiingoSupportedTickers:
    """Implements ``sources.base.Source``. The request key is ignored (one file)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``tiingo`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(URL)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        listings, dropped = parse_listings(payload)
        return Normalized(
            session_date=request.session_date,
            tables={},
            notes={f"dropped_{k}": v for k, v in dropped.items()},
            parsed={TABLE: listings},
        )
