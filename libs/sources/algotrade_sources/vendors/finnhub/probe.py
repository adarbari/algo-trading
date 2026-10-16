"""Finnhub's access probe (``FinnhubProbe``): one request per analyst endpoint, for two names, so
``analyst-probe`` can record which of them this key's plan serves (ADR 0068).

``AAPL`` (a mega-cap: the endpoint names) and ``CHWY`` (a mid-cap of the event-sensitivity scope:
the names with ``@broad``), so a plan that covers only the large names shows. Verified 2026-10-16
on the free plan for AAPL: ``recommendation`` answers; ``price_target`` answers 403 (``You don't
have access to this resource``: premium). The plan can change, so this is a probe: the table
``analyst/vendor_access`` is what later tasks read, never this list.
"""

from algotrade_sources.framework.access import AccessProbe
from algotrade_sources.vendors.finnhub.client import SOURCE, url

PROBE_SYMBOL = "AAPL"  # a large-cap every plan covers: an empty answer for it is a limit
BROAD_SYMBOL = "CHWY"  # a mid-cap of the scope list
BROAD = "@broad"


def endpoints(symbol: str, suffix: str = "") -> dict[str, str]:
    """The probe's endpoint name -> URL for ``symbol``."""
    return {
        f"recommendation{suffix}": url("stock/recommendation", symbol=symbol),
        f"price_target{suffix}": url("stock/price-target", symbol=symbol),
    }


ENDPOINTS = {**endpoints(PROBE_SYMBOL), **endpoints(BROAD_SYMBOL, BROAD)}


class FinnhubProbe(AccessProbe):
    name = SOURCE
    endpoints = ENDPOINTS
