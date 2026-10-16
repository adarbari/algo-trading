"""FMP's access probe (``FmpProbe``): one request per endpoint the analyst feature groups may use,
for AAPL, so ``analyst-probe`` can record which of them this key's plan serves (ADR 0068).

Verified 2026-10-16 on the free plan: ``quote``, ``estimates_annual``, ``price_targets``,
``ratings_summary`` and ``grades`` answer; ``estimates_quarter`` answers 402 (``Premium Query
Parameter``: a premium ``period``). The plan can change, which is why this is a probe and not a
constant: the table ``analyst/vendor_access`` is what later tasks read, never this list.
"""

from algotrade_sources.framework.access import AccessProbe
from algotrade_sources.vendors.fmp.client import SOURCE, url

PROBE_SYMBOL = "AAPL"  # a large-cap every plan covers: an empty answer for it is a limit
ENDPOINTS = {
    "quote": url("quote", symbol=PROBE_SYMBOL),
    "estimates_annual": url(
        "analyst-estimates", symbol=PROBE_SYMBOL, period="annual", page=0, limit=1
    ),
    "estimates_quarter": url(
        "analyst-estimates", symbol=PROBE_SYMBOL, period="quarter", page=0, limit=1
    ),
    "price_targets": url("price-target-consensus", symbol=PROBE_SYMBOL),
    "ratings_summary": url("grades-consensus", symbol=PROBE_SYMBOL),
    "grades": url("grades", symbol=PROBE_SYMBOL, limit=1),
}


class FmpProbe(AccessProbe):
    name = SOURCE
    endpoints = ENDPOINTS
