"""SEC SIC codes -> a coarse market sector (best effort) and the SIC division (official).

The SEC classifies every filer with a 4-digit SIC code. SIC divisions (``Manufacturing``,
``Services``…) are too broad for screening, so ``sector`` maps code ranges to familiar market
sectors (Technology, Health Care…), falling back to a sector per division. The mapping is a
heuristic, not a vendor classification: ``industry`` keeps the SEC's own SIC description.
Codes we cannot place (and funds without a SIC code) stay ``None`` (UNKNOWN to selections).
"""

# (first, last, sector): checked in order, first match wins, so specific ranges come first.
SECTOR_RANGES: tuple[tuple[int, int, str], ...] = (
    (1200, 1399, "Energy"),  # coal, crude petroleum and natural gas, drilling and services
    (2910, 2999, "Energy"),  # petroleum refining
    (4610, 4619, "Energy"),  # pipelines
    (2830, 2836, "Health Care"),  # drugs, biologics
    (3841, 3851, "Health Care"),  # medical instruments and supplies
    (5047, 5047, "Health Care"),
    (5122, 5122, "Health Care"),
    (8000, 8099, "Health Care"),  # health services
    (8731, 8731, "Health Care"),  # commercial physical and biological research
    (3570, 3579, "Technology"),  # computers and office equipment
    (3661, 3679, "Technology"),  # communications equipment, semiconductors, components
    (3820, 3829, "Technology"),  # measuring and control instruments
    (7370, 7379, "Technology"),  # software and computer services
    (2710, 2741, "Communication Services"),  # publishing
    (4800, 4899, "Communication Services"),  # telecom, broadcasting, cable
    (7810, 7841, "Communication Services"),  # motion pictures
    (4950, 4959, "Industrials"),  # sanitary and refuse services
    (4900, 4999, "Utilities"),
    (6500, 6599, "Real Estate"),
    (6798, 6798, "Real Estate"),  # REITs
    (6000, 6799, "Financials"),
    (2000, 2199, "Consumer Staples"),  # food, beverages, tobacco
    (2840, 2844, "Consumer Staples"),  # soap, cleaners, cosmetics
    (5140, 5159, "Consumer Staples"),  # groceries, farm products (wholesale)
    (5400, 5499, "Consumer Staples"),  # food stores
    (5912, 5912, "Consumer Staples"),  # drug stores
    (2200, 2399, "Consumer Discretionary"),  # textiles and apparel
    (2500, 2599, "Consumer Discretionary"),  # furniture
    (3630, 3652, "Consumer Discretionary"),  # household appliances, audio and video
    (3710, 3716, "Consumer Discretionary"),  # motor vehicles
    (3940, 3949, "Consumer Discretionary"),  # toys and sporting goods
    (7000, 7099, "Consumer Discretionary"),  # hotels
    (7900, 7999, "Consumer Discretionary"),  # amusement and recreation
    (1000, 1099, "Materials"),  # metal mining
    (1400, 1499, "Materials"),  # non-metallic minerals
    (2400, 2499, "Materials"),  # lumber and wood
    (2600, 2699, "Materials"),  # paper
    (2800, 2899, "Materials"),  # chemicals (after drugs and cosmetics)
    (3200, 3399, "Materials"),  # glass, stone, concrete, primary metals
)
# (first, last, division, fallback sector): the official SIC divisions.
DIVISIONS: tuple[tuple[int, int, str, str], ...] = (
    (100, 999, "Agriculture, Forestry and Fishing", "Consumer Staples"),
    (1000, 1499, "Mining", "Materials"),
    (1500, 1799, "Construction", "Industrials"),
    (2000, 3999, "Manufacturing", "Industrials"),
    (4000, 4999, "Transportation, Communications and Utilities", "Industrials"),
    (5000, 5199, "Wholesale Trade", "Industrials"),
    (5200, 5999, "Retail Trade", "Consumer Discretionary"),
    (6000, 6799, "Finance, Insurance and Real Estate", "Financials"),
    (7000, 8999, "Services", "Industrials"),
    (9100, 9729, "Public Administration", "Industrials"),
)


def _code(sic: str | None) -> int | None:
    text = (sic or "").strip()
    return int(text) if text.isdigit() else None


def sic_division(sic: str | None) -> str | None:
    code = _code(sic)
    if code is None:
        return None
    return next((d for lo, hi, d, _ in DIVISIONS if lo <= code <= hi), None)


def sic_sector(sic: str | None) -> str | None:
    """Market sector for a SIC code; ``None`` when unknown (e.g. 9995 non-operating shells)."""
    code = _code(sic)
    if code is None:
        return None
    for lo, hi, sector in SECTOR_RANGES:
        if lo <= code <= hi:
            return sector
    return next((s for lo, hi, _, s in DIVISIONS if lo <= code <= hi), None)
