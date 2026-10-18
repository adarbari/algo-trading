"""Which fund carries which macro signal in ``etf_macro@v1`` (EB E5 extension, ADR 0074).

A signal that is not a bar (a credit spread, the VIX, a country's CAPE, a rate differential) is
a column of the fund an allocation edge trades on it: HYG carries the high-yield spread, SPY the
VIX family, each country fund its own CAPE. The map is data, not configuration: changing it
changes what the stored columns mean, so it is pinned by ``VERSION`` and a fitness test over
``map_hash()`` (a changed map with the same ``VERSION`` fails; bump the group's version, ADR 0023).
Tickers become ids only through ``instruments/symbol_ids`` (ADR 0018).
"""

import hashlib
import json

VERSION = 1  # the group's version this map belongs to

# signal column -> the tickers whose row carries it (the other funds' rows hold null)
SIGNAL_ETFS: dict[str, tuple[str, ...]] = {
    "hy_oas": ("HYG",),
    "ig_oas": ("LQD",),
    "baa10y": ("LQD",),
    "t10y3m": ("IEF", "TLT"),
    "t10y2y": ("IEF", "TLT"),
    "dfii10": ("TIP",),
    "wti": ("USO",),
    "usd_broad": ("UUP",),
    "vix": ("SPY",),
    "vix9d": ("SPY",),
    "vix3m": ("SPY",),
    "vix6m": ("SPY",),
    "vvix": ("SPY",),
    "vx_basis": ("SPY",),
    "vx_roll": ("SPY",),
}
# country fund -> its CAPE series (macro.toml; Barclays' Shiller CAPE file, 26 countries)
CAPE_ETFS: dict[str, str] = {
    "EWA": "CAPE_AUSTRALIA", "EWZ": "CAPE_BRAZIL", "EWC": "CAPE_CANADA", "MCHI": "CAPE_CHINA",
    "VGK": "CAPE_EUROPE", "EWQ": "CAPE_FRANCE", "EWG": "CAPE_GERMANY",
    "EWH": "CAPE_HONG_KONG", "EWI": "CAPE_ITALY", "INDA": "CAPE_INDIA", "EIS": "CAPE_ISRAEL",
    "EWJ": "CAPE_JAPAN", "EWY": "CAPE_KOREA", "EWW": "CAPE_MEXICO", "EWN": "CAPE_NETHERLANDS",
    "EPOL": "CAPE_POLAND", "ERUS": "CAPE_RUSSIA", "EWS": "CAPE_SINGAPORE",
    "EZA": "CAPE_SOUTH_AFRICA", "EWP": "CAPE_SPAIN", "EWD": "CAPE_SWEDEN",
    "EWL": "CAPE_SWITZERLAND", "EWT": "CAPE_TAIWAN", "TUR": "CAPE_TURKEY", "EWU": "CAPE_UK",
    "SPY": "CAPE_USA",
}  # fmt: skip
# currency fund -> its currency code; fx_carry = that currency's 3-month rate minus the US one
FX_ETFS: dict[str, str] = {
    "FXE": "EUR", "FXY": "JPY", "FXB": "GBP", "FXA": "AUD", "FXC": "CAD", "FXF": "CHF",
}  # fmt: skip
# the OECD 3-month interbank rate (FRED, macro.toml) of each currency with a fresh series; EUR and
# GBP are absent (their latest observation was over 120 days old, 2026-10-18), so FXE's and FXB's
# fx_carry is null until macro.toml has a rate for them (a new entry here is a VERSION bump)
RATE_SERIES: dict[str, str] = {
    "USD": "IR3TIB01USM156N", "JPY": "IR3TIB01JPM156N", "AUD": "IR3TIB01AUM156N",
    "CAD": "IR3TIB01CAM156N", "CHF": "IR3TIB01CHM156N",
}  # fmt: skip


def carriers() -> tuple[str, ...]:
    """Every ticker that has a row, sorted."""
    found = {t for tickers in SIGNAL_ETFS.values() for t in tickers}
    return tuple(sorted(found | CAPE_ETFS.keys() | FX_ETFS.keys()))


def map_hash() -> str:
    """A hash of the whole map: the fitness test pins it against ``VERSION``."""
    doc = [SIGNAL_ETFS, CAPE_ETFS, FX_ETFS, RATE_SERIES]
    return hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
