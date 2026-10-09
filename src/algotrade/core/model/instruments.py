"""Instrument identifiers (ADR 0009, ADR 0018).

- Equities and ETFs: ``EQ:<composite FIGI>`` (``EQ:BBG000B9XRY4``) when the FIGI is known,
  else, for a historic listing with a vendor permanent id, ``EQ:TIINGO:<permaTicker>``
  (ADR 0018 amendment 2026-10-08), else the symbol id ``EQ:<SYMBOL>``. A FIGI id never
  changes, whatever the ticker does.
- Options: ``OPT:<OCC symbol>`` (``OPT:SPY261231C00586000``).
- Index levels and macro series (ADR 0048): ``IDX:<KEY>`` (``IDX:SPX``) and ``MACRO:<KEY>``
  (``MACRO:T10Y3M``), not tradable; the keys come from ``config/site/macro.toml``.
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
    MACRO = "MACRO"  # an economic series (ADR 0048), not tradable
    OPTION = "OPT"
    FUTURE = "FUT"
    RATE = "RATE"  # a reference interest rate (one tenor of a yield curve), not tradable
    MARKET = "MKT"  # a whole market (the row of a market-entity feature group), not tradable


def instrument_id(asset_class: AssetClass, symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise ValueError("symbol must not be empty")
    return f"{asset_class.value}:{cleaned}"


PERMA_NAMESPACE = "TIINGO"


def _given(value: str | None) -> bool:
    return value is not None and bool(str(value).strip())


def equity_id(symbol: str, figi: str | None = None, perma_ticker: str | None = None) -> str:
    """The id rule for equities and ETFs: FIGI-based when a composite FIGI is known, else
    ``EQ:TIINGO:<permaTicker>`` when the vendor's permanent id is, else the symbol id.
    A symbol never contains ``:`` (the namespaced key cannot collide with one)."""
    if _given(figi):
        return instrument_id(AssetClass.EQUITY, str(figi))
    if _given(perma_ticker):
        return instrument_id(AssetClass.EQUITY, f"{PERMA_NAMESPACE}:{str(perma_ticker).strip()}")
    if ":" in symbol:
        raise ValueError(f"a symbol never contains ':': {symbol!r}")
    return instrument_id(AssetClass.EQUITY, symbol)


def is_perma_id(instrument: str) -> bool:
    """True for ``EQ:TIINGO:<permaTicker>``: a listing outside ``symbol_history`` (equity_id)."""
    parts = instrument.split(":")
    return (
        len(parts) == 3
        and parts[0] == AssetClass.EQUITY.value
        and parts[1] == PERMA_NAMESPACE
        and bool(parts[2])
    )


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


def index_id(key: str) -> str:
    """The id of an index level series (``IDX:SPX``); the only place ``IDX:`` ids are minted."""
    return instrument_id(AssetClass.INDEX, key)


def macro_id(key: str) -> str:
    """The id of an economic series (``MACRO:T10Y3M``); the only place ``MACRO:`` ids are
    minted."""
    return instrument_id(AssetClass.MACRO, key)


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
