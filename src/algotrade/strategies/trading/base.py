"""The strategy contract."""

from abc import ABC, abstractmethod

from algotrade.core.model.types import TargetWeights
from algotrade.core.views.market_view import MarketView


class Strategy(ABC):
    """Base class for all strategies.

    Subclasses are constructed with keyword parameters only, so they can be built from
    config files / CLI flags, and must be deterministic given the same inputs.
    """

    name: str = "unnamed"

    @property
    def warmup_bars(self) -> int:
        """Bars of history required before ``on_bar`` is first called."""
        return 1

    @abstractmethod
    def on_bar(self, view: MarketView) -> TargetWeights | None:
        """Decide target weights at the close of the current bar.

        Returning ``None`` means "no change". Returning a mapping means "rebalance to
        exactly these weights"; instruments left out are closed.
        """

    def params(self) -> dict[str, float | int | str]:
        """Parameters that identify this configuration (used in reports and baselines)."""
        return {}
