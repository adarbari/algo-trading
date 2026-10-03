"""Instrument identifiers.

Interim scheme until the reference store (ADR 0009) assigns ids: ``<CLASS>:<SYMBOL>``,
for example ``EQ:SPY`` or ``OPT:SPY261231C00586000``. Every stored row is keyed by these
ids, never by a raw ticker string, so switching to reference-store ids later is a mapping
change rather than a schema change.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class AssetClass(StrEnum):
    EQUITY = "EQ"  # common stocks, ADRs and ETFs (security type is a reference attribute)
    INDEX = "IDX"
    OPTION = "OPT"
    FUTURE = "FUT"


def instrument_id(asset_class: AssetClass, symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise ValueError("symbol must not be empty")
    return f"{asset_class.value}:{cleaned}"


def symbol_of(instrument: str) -> str:
    _, sep, symbol = instrument.partition(":")
    if not sep or not symbol:
        raise ValueError(f"not an instrument id: {instrument!r}")
    return symbol


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
