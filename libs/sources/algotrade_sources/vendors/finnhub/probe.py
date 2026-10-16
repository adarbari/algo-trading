"""Finnhub's access probe (``FinnhubProbe``): one request per analyst endpoint, for AAPL, so
``analyst-probe`` can record which of them this key's plan serves (ADR 0068).

Verified 2026-10-16 on the free plan: ``recommendation`` answers; ``price_target`` answers 403
(``You don't have access to this resource``: premium). The plan can change, so this is a probe:
the table ``analyst/vendor_access`` is what later tasks read, never this list.
"""

from algotrade_sources.framework.access import AccessProbe
from algotrade_sources.vendors.finnhub.client import SOURCE, url

PROBE_SYMBOL = "AAPL"  # a large-cap every plan covers: an empty answer for it is a limit
ENDPOINTS = {
    "recommendation": url("stock/recommendation", symbol=PROBE_SYMBOL),
    "price_target": url("stock/price-target", symbol=PROBE_SYMBOL),
}


class FinnhubProbe(AccessProbe):
    name = SOURCE
    endpoints = ENDPOINTS
