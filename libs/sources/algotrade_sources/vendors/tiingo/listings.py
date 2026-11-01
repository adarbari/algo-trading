"""Tiingo's supported-tickers file: every ticker it ever listed with its dates
(``TiingoSupportedTickers``; the listing history behind the winners study, ADR 0018
amendment 2026-10-08, edges ED6).

``https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip`` is one public ZIP with
one CSV, ``supported_tickers.csv``: ``ticker, exchange, assetType, priceCurrency, startDate,
endDate``. ``startDate`` / ``endDate`` are the first and last day Tiingo has prices for the
ticker; ``endDate`` of a live name is a recent day, and blank when Tiingo has no prices. It
has no ``permaTicker`` (that comes from the per-ticker meta endpoint, a later adapter), so
``perma_ticker`` is empty here and the task decides ids.

Every file row is returned (owner tenet 2026-11-01: nothing a free source sends is discarded);
``scope_reason`` says why a row is outside the universe's scope, null when it is in. In scope:
USD, the exchanges ``EXCHANGES`` (Tiingo's ``NYSE MKT`` / ``NYSE ARCA`` are our ``AMEX`` /
``ARCA``), asset type Stock or ETF, a plain ticker (``TICKER``: share classes ``BRK-B`` are kept;
the file also lists preferreds, units, notes and expiring warrants under tickers such as
``BC/PA``, ``CFX 5.75`` or ``CAPTW(EXP20260807)``, which are not names we trade) and a parseable
``startDate``. A row failing several tests carries the first reason (the order of the tests in
``parse_listings``: ``not_usd``, ``other_exchange``, ``other_asset_type``, ``no_start_date``,
``no_ticker``, ``odd_ticker``). Of two in-scope rows with one (ticker, startDate) the one still
open, else the longest, stays in scope and the other is ``duplicate_start``. An out-of-scope row
keeps the
file's own exchange and asset type text where ``EXCHANGES`` / ``ASSET_TYPES`` do not map it (the
successor of a bankrupt name sits under an OTC exchange: the listing merge reads those rows for
the start of a Massive-only record). A row repeating another on every key column is dropped and
counted (``dropped_exact_duplicate``). The counts per reason are in ``Normalized.notes``
(``out_of_scope_<reason>``). Recorded 2026-10-08 (108,972 rows, 24,550 of them in scope at the
first pull; a live name's ``endDate`` is the file's latest day). The file is one request, so the
shared ``tiingo`` limiter is not a constraint.
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
    "scope_reason",
]
KEY = ["ticker", "exchange", "asset_type", "start_date", "end_date"]  # the table key, bar source
DUPLICATE_START = "duplicate_start"  # the scope reason of the loser of a (ticker, start) pair
EXACT_DUPLICATE = "exact_duplicate"  # a row repeating another on KEY: dropped, counted


def read_listing_csv(payload: bytes) -> pd.DataFrame:
    """The ZIP (or the bare CSV) -> the file's rows as text, ``HEADER`` columns checked."""
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
    return raw


def _text(values: pd.Series) -> pd.Series:
    """The text, a blank one as ``None``."""
    return values.where(values != "", None)


def parse_listings(payload: bytes) -> tuple[pd.DataFrame, dict[str, int]]:
    """The ZIP (or the bare CSV) -> (every row as ``COLUMNS``, rows per ``scope_reason`` plus the
    exact duplicates dropped under ``EXACT_DUPLICATE``)."""
    raw = read_listing_csv(payload)
    ticker = raw["ticker"].str.strip().str.upper()
    exchange_text = raw["exchange"].str.strip()
    exchange = exchange_text.str.upper().map(EXCHANGES)
    asset_text = raw["assetType"].str.strip()
    asset = asset_text.str.upper().map(ASSET_TYPES)
    currency = raw["priceCurrency"].str.strip().str.upper()
    start = pd.to_datetime(raw["startDate"].str.strip(), errors="coerce")
    end = pd.to_datetime(raw["endDate"].str.strip(), errors="coerce")
    reasons = {
        "not_usd": currency != "USD",
        "other_exchange": exchange.isna(),
        "other_asset_type": asset.isna(),
        "no_start_date": start.isna(),
        "no_ticker": ticker == "",
        "odd_ticker": (ticker != "") & ~ticker.str.fullmatch(TICKER),
    }
    scope = pd.Series(None, index=raw.index, dtype=object)
    counts: dict[str, int] = {}
    for reason, mask in reasons.items():  # each row counted under its first reason
        first = mask & scope.isna()
        counts[reason] = int(first.sum())
        scope[first] = reason
    # The latest endDate among the rows in scope is the pull's last day: still listed (open). Not
    # the file's: Chinese listings (CNY, SHE / SHG) can be a day ahead.
    end = end.where(end != end[scope.isna()].max())
    frame = pd.DataFrame(
        {
            "ticker": _text(ticker),
            "exchange": _text(exchange.where(exchange.notna(), exchange_text)),
            "asset_type": _text(asset.where(asset.notna(), asset_text)),
            "price_currency": _text(currency),
            "start_date": start.dt.date.where(start.notna(), None),
            "end_date": end.dt.date.where(end.notna(), None),
            "perma_ticker": "",
            "scope_reason": scope,
        }
    )
    unique = frame.drop_duplicates(KEY)
    counts[EXACT_DUPLICATE] = len(frame) - len(unique)
    # The file lists a few (ticker, startDate) twice (a Stock and an ETF row, a re-listing on its
    # first day): the row still open, else the one that lasted longest, stays in scope.
    live = unique[unique["scope_reason"].isna()]
    ordered = live.assign(_last=live["end_date"].fillna(date.max)).sort_values(
        ["ticker", "start_date", "_last"], kind="stable"
    )
    losers = ordered.index[ordered.duplicated(["ticker", "start_date"], keep="last")]
    lost = unique.index.isin(losers)
    unique = unique.assign(scope_reason=unique["scope_reason"].mask(lost, DUPLICATE_START))
    counts[DUPLICATE_START] = len(losers)
    out = unique.sort_values(["ticker", "start_date"], kind="stable").reset_index(drop=True)
    scoped = out["scope_reason"]
    out = out.assign(scope_reason=scoped.astype(object).where(scoped.notna(), None))
    return out[COLUMNS], counts


class TiingoSupportedTickers:
    """Implements ``sources.base.Source``. The request key is ignored (one file)."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``tiingo`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(URL)

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        listings, counts = parse_listings(payload)
        notes = {f"out_of_scope_{k}": v for k, v in counts.items() if k != EXACT_DUPLICATE}
        notes["dropped_exact_duplicate"] = counts[EXACT_DUPLICATE]
        return Normalized(
            session_date=request.session_date,
            tables={},
            notes=notes,
            parsed={TABLE: listings},
        )
