"""The broker contract shared by simulated, paper and live implementations."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol

from algotrade.core.model.types import Fill, Order


class Broker(Protocol):
    def submit(self, orders: Sequence[Order]) -> None:
        """Queue orders for execution at the next opportunity."""

    def execute_pending(
        self, open_prices: Mapping[str, float], timestamp: datetime, buying_power: float
    ) -> list[Fill]:
        """Execute queued orders at this bar's open without exceeding ``buying_power``."""
