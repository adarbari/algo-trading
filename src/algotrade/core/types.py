"""Immutable value objects that flow between layers."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# Target portfolio weights keyed by symbol, as a fraction of equity (1.0 == 100%).
# Negative weights are shorts. Symbols that are absent are treated as 0.
type TargetWeights = Mapping[str, float]


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


@dataclass(frozen=True, slots=True)
class Order:
    """A market order. ``quantity`` is always positive; direction lives in ``side``."""

    symbol: str
    side: Side
    quantity: float
    created_at: datetime

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {self.quantity}")
        if self.created_at.tzinfo is None:
            raise ValueError("Order.created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Fill:
    """An executed (possibly simulated) trade."""

    symbol: str
    side: Side
    quantity: float
    price: float
    commission: float
    timestamp: datetime

    @property
    def signed_quantity(self) -> float:
        return self.side.sign * self.quantity

    @property
    def notional(self) -> float:
        return self.quantity * self.price
