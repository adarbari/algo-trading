"""FMP price targets and ratings (``FmpPriceTargets``, ``FmpRatings``).

``/stable/price-target-consensus?symbol=S`` answers one record: ``symbol``, ``targetHigh``,
``targetLow``, ``targetConsensus``, ``targetMedian``. ``/stable/grades-consensus?symbol=S``
answers one record: ``symbol``, ``strongBuy``, ``buy``, ``hold``, ``sell``, ``strongSell`` (the
analyst counts) and ``consensus`` (the label, ``Buy``). Both verified 2026-10-16 on a free key.
An unknown symbol answers 402 (``Premium Query Parameter``): that is a plan
limit, not "no data", so ``fetch`` raises it (``HttpError``, not retried: ``refused``).

Request key: the symbol. ``normalize`` returns ``parsed["targets"]`` / ``parsed["ratings"]``:
nothing is stored from here yet (ADR 0068).
"""

import pandas as pd

from algotrade_sources.framework.base import FetchRequest, Normalized
from algotrade_sources.framework.http import Http
from algotrade_sources.vendors.fmp.client import SOURCE, rows, url, vendor_symbol

TARGET_COLUMNS = ["symbol", "target_high", "target_low", "target_consensus", "target_median"]
RATING_COLUMNS = ["symbol", "strong_buy", "buy", "hold", "sell", "strong_sell", "consensus"]
_TARGET_FIELDS = ("targetHigh", "targetLow", "targetConsensus", "targetMedian")
_RATING_COUNTS = ("strongBuy", "buy", "hold", "sell", "strongSell")


def parse_targets(payload: bytes) -> pd.DataFrame:
    """The record(s) -> ``TARGET_COLUMNS`` (prices as floats; a record without a symbol is
    dropped)."""
    records = [r for r in rows(payload) if str(r.get("symbol") or "").strip()]
    frame = pd.DataFrame(
        {
            "symbol": [str(r["symbol"]).strip().upper() for r in records],
            **{
                col: pd.to_numeric(pd.Series([r.get(src) for r in records]), errors="coerce")
                for col, src in zip(TARGET_COLUMNS[1:], _TARGET_FIELDS, strict=True)
            },
        }
    )
    return frame[TARGET_COLUMNS].reset_index(drop=True)


def parse_ratings(payload: bytes) -> pd.DataFrame:
    """The record(s) -> ``RATING_COLUMNS`` (counts as integers, a missing count null)."""
    records = [r for r in rows(payload) if str(r.get("symbol") or "").strip()]
    frame = pd.DataFrame(
        {
            "symbol": [str(r["symbol"]).strip().upper() for r in records],
            **{
                col: pd.array([r.get(src) for r in records], dtype="Int64")
                for col, src in zip(RATING_COLUMNS[1:6], _RATING_COUNTS, strict=True)
            },
            "consensus": [str(r.get("consensus") or "") or None for r in records],
        }
    )
    return frame[RATING_COLUMNS].reset_index(drop=True)


class FmpPriceTargets:
    """Implements ``sources.base.Source``. Request key: the symbol."""

    name = SOURCE
    dataset = "price_targets"

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``fmp`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(url("price-target-consensus", symbol=vendor_symbol(request.key)))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(request.session_date, {}, {}, {"targets": parse_targets(payload)})


class FmpRatings:
    """Implements ``sources.base.Source``. Request key: the symbol."""

    name = SOURCE
    dataset = "ratings"

    def __init__(self, http: Http) -> None:
        self._http = http  # paced by the shared ``fmp`` limiter (sources.toml)

    def fetch(self, request: FetchRequest) -> bytes | None:
        return self._http.get(url("grades-consensus", symbol=vendor_symbol(request.key)))

    def normalize(self, request: FetchRequest, payload: bytes) -> Normalized | None:
        return Normalized(request.session_date, {}, {}, {"ratings": parse_ratings(payload)})
