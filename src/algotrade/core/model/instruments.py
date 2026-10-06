"""Instrument identifiers (ADR 0009, ADR 0018).

- Equities and ETFs: ``EQ:<composite FIGI>`` (``EQ:BBG000B9XRY4``) when the FIGI is known,
  else the symbol id ``EQ:<SYMBOL>``. A FIGI id never changes, whatever the ticker does.
- Options: ``OPT:<OCC symbol>`` (``OPT:SPY261231C00586000``).
- Reference rates: ``RATE:<curve>-<tenor>`` (``RATE:UST-3M``, a Treasury par yield tenor).
- Markets: ``MKT:<market>`` (``MKT:US``), the one row per session of a market-entity feature
  group (``rollups/market/<name>@v<N>``; ADR 0047). Not tradable; only ``market_id`` builds it.

Every stored row is keyed by these ids, never by a raw ticker. Code that has a vendor ticker
resolves it through ``data.resolver.SymbolResolver``; only ``equity_id`` builds ``EQ:`` ids.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class AssetClass(StrEnum):
    EQUITY = "EQ"  # common stocks, ADRs and ETFs (security type is a reference attribute)
    INDEX = "IDX"
    OPTION = "OPT"
    FUTURE = "FUT"
    RATE = "RATE"  # a reference interest rate (one tenor of a yield curve), not tradable
    MARKET = "MKT"  # a whole market (the row of a market-entity feature group), not tradable


def instrument_id(asset_class: AssetClass, symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise ValueError("symbol must not be empty")
    return f"{asset_class.value}:{cleaned}"


def equity_id(symbol: str, figi: str | None = None) -> str:
    """The id rule for equities and ETFs: FIGI-based when a composite FIGI is known."""
    has_figi = figi is not None and bool(str(figi).strip())
    return instrument_id(AssetClass.EQUITY, str(figi) if has_figi else symbol)


def market_id(market: str) -> str:
    """The id of a whole market's row in a market-entity feature group: ``market_id("US")``
    is ``MKT:US`` (ADR 0047). The one place the ``MKT:`` prefix is built."""
    return instrument_id(AssetClass.MARKET, market)


def is_figi_id(instrument: str, figi: str | None) -> bool:
    """True when ``instrument`` is the FIGI-based id for ``figi``."""
    return figi is not None and bool(str(figi).strip()) and instrument == equity_id("", figi)


def key_of(instrument: str) -> str:
    """The part after the class prefix: a symbol, a FIGI or an OCC symbol (never display it
    as a ticker; read ``symbol`` from the reference instead)."""
    _, sep, key = instrument.partition(":")
    if not sep or not key:
        raise ValueError(f"not an instrument id: {instrument!r}")
    return key


def pad_cik(value: object) -> str | None:
    """An SEC CIK in any form (``320193``, ``"0000320193"``, ``320193.0``) -> 10 digits, else
    ``None``. Reference rows and SEC payloads carry CIKs in different forms; join on this."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(10) if text.isdigit() and int(text) > 0 else None


@dataclass(frozen=True, slots=True)
class Instrument:
    """The contract terms engines need. Full reference data lives in storage (L1)."""

    instrument_id: str
    symbol: str
    asset_class: AssetClass = AssetClass.EQUITY
    multiplier: float = 1.0
    currency: str = "USD"
    tick_size: float = 0.01

    def __post_init__(self) -> None:
        if self.multiplier <= 0:
            raise ValueError(f"{self.instrument_id}: multiplier must be positive")
        if self.tick_size <= 0:
            raise ValueError(f"{self.instrument_id}: tick_size must be positive")


def multipliers(instruments: Iterable[Instrument]) -> dict[str, float]:
    return {i.instrument_id: i.multiplier for i in instruments}
