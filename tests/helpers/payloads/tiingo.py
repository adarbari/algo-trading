"""Tiingo payloads: the daily prices BUILT FROM THE DOCUMENTATION (not recorded), and the
supported-tickers file RECORDED (the slice at the end).

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


# RECORDED: a trimmed slice of the real ``supported_tickers.zip`` (Tiingo, downloaded 2026-10-08,
# 108,972 rows; internal / personal licence, so only 244 rows are committed, not the file). The
# rows are exactly as received, in file order, picked with a fixed seed to hold what the adapter
# and the sample runner must handle: live names (AAPL, MSFT, SPY, 2026-10-08 is the file's latest
# day), delisted names by year of ``endDate`` 2011-2020 (TWTR), tickers recycled by several
# listings (AAC with overlapping dates, AAAP a stock then an ETF), NYSE MKT / NYSE ARCA / BATS
# rows, and the rows the adapter drops (CNY / HKD / AUD prices, PINK / OTCBB / SHE / mutual-fund
# exchanges, preferreds and notes under tickers such as ``BC/PA``).
SUPPORTED_TICKERS_SLICE = (
    REPO_ROOT / "tests" / "fixtures" / "sources" / "tiingo" / ("supported_tickers_slice.csv")
)


def supported_tickers_csv() -> bytes:
    return SUPPORTED_TICKERS_SLICE.read_bytes()


def supported_tickers_zip() -> bytes:
    """The recorded slice zipped as Tiingo ships it (one ``supported_tickers.csv``)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("supported_tickers.csv", supported_tickers_csv())
    return buffer.getvalue()
