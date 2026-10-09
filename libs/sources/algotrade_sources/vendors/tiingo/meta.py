"""Tiingo's fundamentals meta: which listings ever used a ticker, with their permanent id
(``TiingoListingMeta``; ADR 0018 amendment 2026-10-08, edges ED6).

``https://api.tiingo.com/tiingo/fundamentals/meta?tickers=a,b,...`` answers a JSON list with
ONE object per listing that ever used each requested ticker: ``permaTicker`` (``US000000041372``,
stable across ticker changes), ``ticker`` (lowercase), ``name``, ``isActive`` and
``dataProviderPermaTicker``; the sector, industry and similar fields are gated (a string
"Field not available for free/evaluation") and ignored. A recycled ticker therefore answers with
several rows: ``prm`` -> PRIMEDIA (inactive) and Perimeter (active). ``permaTicker`` is also the
key of ``/tiingo/daily/<permaTicker>/prices``, which serves that listing's own bars.

The request key is the tickers, comma-separated (the task batches them, 100 at a time); the key
travels in an ``Authorization: Token`` header set on the transport. Tickers Tiingo does not know
are simply absent from the answer. The adapter returns every row; which listing a row belongs to is
``tasks/reference/instrument_ids.match_perma``'s decision, never this module's.
"""

import json
from urllib.parse import quote

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http

SOURCE = "tiingo"
DATASET = "fundamentals_meta"
TABLE = "perma_meta"  # a key of ``Normalized.parsed``: nothing is stored from here
HOST = "https://api.tiingo.com"
URL = HOST + "/tiingo/fundamentals/meta?tickers={tickers}"
COLUMNS = ["ticker", "perma_ticker", "name", "is_active", "data_provider_perma_ticker"]


def vendor_symbol(ticker: str) -> str:
    """Our ticker -> the form the meta endpoint takes: lowercase, a share class with a hyphen."""
    return ticker.strip().lower().replace(".", "-")


def parse_meta(payload: bytes) -> pd.DataFrame:
    """The JSON list -> ``COLUMNS`` (``ticker`` upper-case, ``is_active`` a bool); a row with no
    ``permaTicker`` or ticker is dropped, a repeated ``permaTicker`` kept once."""
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError(f"expected a JSON list of listings, got {str(rows)[:120]!r}")
    frame = pd.DataFrame(
        rows,
        columns=["ticker", "permaTicker", "name", "isActive", "dataProviderPermaTicker"],
    )
    frame.columns = pd.Index(COLUMNS)
    for column in ("ticker", "perma_ticker", "name", "data_provider_perma_ticker"):
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    frame["ticker"] = frame["ticker"].str.upper()
    frame["is_active"] = frame["is_active"].map(lambda v: v is True or str(v).lower() == "true")
    kept = frame[(frame["ticker"] != "") & (frame["perma_ticker"] != "")]
    return kept.drop_duplicates(["ticker", "perma_ticker"]).reset_index(drop=True)


class TiingoListingMeta:
    """Implements ``sources.base.Source``. Request key: the tickers, comma-separated."""

    name = SOURCE
    dataset = DATASET

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``tiingo`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        tickers = [vendor_symbol(t) for t in request.key.split(",") if t.strip()]
        return self._http.get(URL.format(tickers=quote(",".join(tickers), safe=",-")))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(
            session_date=request.session_date,
            tables={},
            notes={},
            parsed={TABLE: parse_meta(payload)},
        )
