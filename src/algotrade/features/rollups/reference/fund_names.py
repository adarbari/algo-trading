"""What a leveraged or inverse fund's NAME says it tracks: the ticker of one stock, or the kind of
basket (index, sector, commodity). Pure text rules for ``fund_reference@v1`` (ADR 0050), used
when the holdings table does not settle it.

A ticker is read only in the spellings leveraged-fund names use, with the ticker in upper case
(a company written "Tesla" is not read): ``Daily TSLA Bull 2X`` (Direxion), ``2x Long TSLA
Daily`` / ``2X Long TSLA`` (GraniteShares, Leverage Shares, Tradr, Defiance) and ``TSLA 2X Bull``.
A name written wholly in capitals is never read for a ticker (``DAILY GOLD BULL 2X``: a word is
not told from a ticker). Whether the ticker is listed, and is a stock, is the caller's check
(``SymbolResolver``'s map, never an id built here).
"""

import re

TICKER = r"[A-Z][A-Z0-9]{0,5}(?:\.[A-Z])?"
_LEVER = r"(?i:\d(?:\.\d+)?X)"
_SIDE = r"(?i:long|short|bull|bear|inverse)"
_TICKER_PATTERNS = tuple(
    re.compile(p)
    for p in (
        rf"\b(?i:daily)\s+(?P<t>{TICKER})\s+{_SIDE}\b",  # Direxion Daily TSLA Bull 2X Shares
        rf"\b{_LEVER}\s+{_SIDE}\s+(?P<t>{TICKER})\b",  # GraniteShares 2x Long TSLA Daily ETF
        rf"\b(?P<t>{TICKER})\s+{_LEVER}\s+{_SIDE}\b",  # TSLA 2X Bull
    )
)
# Capitalised words of a fund name that sit where a ticker would: never one.
_NOT_TICKERS = frozenset(
    [
        "ETF",
        "ETN",
        "ETP",
        "FUND",
        "SHARES",
        "DAILY",
        "LONG",
        "SHORT",
        "BULL",
        "BEAR",
        "INDEX",
        "ULTRA",
        "INVERSE",
        "TARGET",
        "STRATEGY",
    ]
)
# Volatility funds track no stock, index or commodity with events of their own.
_VOLATILITY = re.compile(r"\bvix\b|volatility", re.IGNORECASE)
# The first of these that matches names the kind: a sector ("Gold Miners") before a commodity
# ("Gold") before an index ("S&P 500"), the more specific wins.
_KINDS = tuple(
    (kind, re.compile(pattern, re.IGNORECASE))
    for kind, pattern in (
        (
            "sector",
            r"semiconductor|technology|\btech\b|financial|\benergy\b|biotech|health ?care|utilit"
            r"|home ?builder|aerospace|defen[cs]e|real estate|retail|\bbanks?\b|miners|exploration"
            r"|oil (?:&|and) gas|metals|pharma|internet|software|cyber|infrastructure|transport"
            r"|insurance|materials|industrials|consumer|communication|solar|clean|robotic|online",
        ),
        (
            "commodity",
            r"\bgold\b|\bsilver\b|\boil\b|crude|natural gas|\bgas\b|bitcoin|\bether(?:eum)?\b"
            r"|crypto|copper|platinum|palladium|commodit|bullion|\bwheat\b|\bcorn\b|uranium"
            r"|lithium",
        ),
        (
            "index",
            r"s&p|nasdaq|\bqqq|russell|\bdow\b|mid ?cap|small ?cap|large ?cap|\bindex\b|china"
            r"|brazil|india|emerging|europe|japan",
        ),
    )
)


def name_ticker(name: str) -> str | None:
    """The ticker a single-stock fund's name states (``None``: none read, or the name is in
    capitals throughout)."""
    if name.upper() == name:
        return None
    for pattern in _TICKER_PATTERNS:
        for found in pattern.finditer(name):
            if found.group("t") not in _NOT_TICKERS:
                return found.group("t")
    return None


def name_kind(name: str) -> str | None:
    """``sector``, ``commodity``, ``index`` or ``none`` (a volatility fund) from the keywords
    of the name; ``None`` when it says nothing."""
    if _VOLATILITY.search(name):
        return "none"
    for kind, pattern in _KINDS:
        if pattern.search(name):
            return kind
    return None
