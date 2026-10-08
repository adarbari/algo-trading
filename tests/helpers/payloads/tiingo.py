"""Tiingo end-of-day payloads, BUILT FROM THE DOCUMENTATION, not recorded.

``tests/fixtures/sources/tiingo/daily_prices_sample.json`` follows Tiingo's documented response
of ``/tiingo/daily/<ticker>/prices`` (https://www.tiingo.com/documentation/end-of-day): a JSON
list of objects with ``date`` (ISO with a ``T00:00:00.000Z`` time), ``open``, ``high``, ``low``,
``close``, ``volume``, ``adjOpen``, ``adjHigh``, ``adjLow``, ``adjClose``, ``adjVolume``,
``divCash`` and ``splitFactor``. No Tiingo key existed when it was written, so the numbers are
invented (a 4-for-1 split on 2020-08-31, a dividend on 2020-11-06) and the ``adj*`` fields are
deliberately different from the unadjusted ones, to prove they are never stored. Replace it
with a payload recorded on the first real ``bars-history`` run (``raw/source=tiingo``).
"""

import io
import json
import zipfile
from collections.abc import Iterable

from tests.conftest import REPO_ROOT

SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sources" / "tiingo" / "daily_prices_sample.json"


def sample() -> bytes:
    return SAMPLE.read_bytes()


def prices(
    rows: Iterable[tuple[str, float, float, float, float, float]],
    splits: dict[str, float] | None = None,
) -> bytes:
    """rows: (ISO date, open, high, low, close, volume); ``splits``: date -> splitFactor."""
    out = [
        {
            "date": f"{d}T00:00:00.000Z",
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": v,
            "adjOpen": o / 2,
            "adjHigh": h / 2,
            "adjLow": lo / 2,
            "adjClose": c / 2,
            "adjVolume": v * 2,
            "divCash": 0.0,
            "splitFactor": (splits or {}).get(d, 1.0),
        }
        for d, o, h, lo, c, v in rows
    ]
    return json.dumps(out).encode()


# SYNTHETIC: ``supported_tickers.zip`` as DOCUMENTED (https://www.tiingo.com/documentation/
# end-of-day, "supported tickers"): one CSV, header ``ticker,exchange,assetType,priceCurrency,
# startDate,endDate``. Not recorded: every ticker, name and date below is invented, with the
# cases the adapter and ``universe_asof`` must handle: a live name, delisted names, a ticker
# recycled by two companies (RCY) and rows that are filtered out. Replace it with a recording of
# the real file (owner OK for the download) before the ``listing-history`` task joins any
# workflow.
SUPPORTED_TICKERS_SYNTHETIC = """ticker,exchange,assetType,priceCurrency,startDate,endDate
AAA,NYSE,Stock,USD,2000-01-03,2026-10-02
BBB,NASDAQ,Stock,USD,2005-03-01,2013-01-02
RCY,NASDAQ,Stock,USD,2005-01-03,2010-12-31
RCY,NYSE,Stock,USD,2011-03-01,2026-10-02
ETFX,NYSE ARCA,ETF,USD,2008-01-02,2026-10-02
OLDM,NYSE MKT,Stock,USD,2001-05-01,2009-06-30
FRGN,NASDAQ,Stock,CAD,2010-01-04,2026-10-02
PINK,OTCBB,Stock,USD,2010-01-04,2026-10-02
MUTL,NASDAQ,Mutual Fund,USD,2010-01-04,2026-10-02
NODT,NASDAQ,Stock,USD,,
"""


def supported_tickers_zip() -> bytes:
    """The SYNTHETIC file above zipped as Tiingo ships it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("supported_tickers.csv", SUPPORTED_TICKERS_SYNTHETIC)
    return buffer.getvalue()
