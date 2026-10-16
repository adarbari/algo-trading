"""FMP's access probe (``FmpProbe``): one request per endpoint the analyst feature groups may use,
for two names, so ``analyst-probe`` can record which of them this key's plan serves (ADR 0068).

Two names because the free plan's coverage is not the same for every symbol (FMP answers 402 for
symbols outside its free sample set): ``AAPL``, a mega-cap in that set (the endpoint names), and
``CHWY``, a mid-cap of the event-sensitivity scope (``config/site/events/scope.toml``) that is
the probe's test of what the scoped pull can use (the endpoint names with ``@broad``). The probe
only reports; where the real boundary lies is read from ``analyst/vendor_access``, not assumed.

Verified 2026-10-16 on the free plan for AAPL: ``quote``, ``estimates_annual``, ``price_targets``,
``ratings_summary`` and ``grades`` answer; ``estimates_quarter`` answers 402 (``Premium Query
Parameter``: a premium ``period``). The plan can change, which is why this is a probe and not a
constant: the table is what later tasks read, never this list.
"""

from algotrade_sources.framework.access import AccessProbe
from algotrade_sources.vendors.fmp.client import SOURCE, url

PROBE_SYMBOL = "AAPL"  # a mega-cap in FMP's free sample set: an empty answer for it is a limit
BROAD_SYMBOL = "CHWY"  # a mid-cap of the scope list: what the scoped pull can reach
BROAD = "@broad"


def endpoints(symbol: str, suffix: str = "") -> dict[str, str]:
    """The probe's endpoint name -> URL (no key) for ``symbol``."""
    return {
        f"quote{suffix}": url("quote", symbol=symbol),
        f"estimates_annual{suffix}": url(
            "analyst-estimates", symbol=symbol, period="annual", page=0, limit=1
        ),
        f"estimates_quarter{suffix}": url(
            "analyst-estimates", symbol=symbol, period="quarter", page=0, limit=1
        ),
        f"price_targets{suffix}": url("price-target-consensus", symbol=symbol),
        f"ratings_summary{suffix}": url("grades-consensus", symbol=symbol),
        f"grades{suffix}": url("grades", symbol=symbol, limit=1),
    }


ENDPOINTS = {**endpoints(PROBE_SYMBOL), **endpoints(BROAD_SYMBOL, BROAD)}


class FmpProbe(AccessProbe):
    name = SOURCE
    endpoints = ENDPOINTS
