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

import json
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
