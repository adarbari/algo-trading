"""Transaction cost model. Backtests without costs are fiction."""

from dataclasses import dataclass

from algotrade.core.model.types import Side


@dataclass(frozen=True)
class CostModel:
    commission_bps: float = 1.0  # proportional commission, basis points of notional
    min_commission: float = 0.0  # per-order floor
    slippage_bps: float = 5.0  # adverse price move vs the reference price

    def fill_price(self, side: Side, reference_price: float) -> float:
        return reference_price * (1 + side.sign * self.slippage_bps / 10_000)

    def commission(self, notional: float) -> float:
        return max(self.min_commission, abs(notional) * self.commission_bps / 10_000)

    @classmethod
    def free(cls) -> "CostModel":
        return cls(commission_bps=0.0, min_commission=0.0, slippage_bps=0.0)
