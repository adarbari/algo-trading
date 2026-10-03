"""Hard portfolio limits applied to every strategy's target weights."""

from dataclasses import dataclass

from algotrade.core.errors import ConfigurationError
from algotrade.core.types import TargetWeights


@dataclass(frozen=True)
class RiskLimits:
    max_position_weight: float = 1.0
    max_gross_exposure: float = 1.0
    allow_short: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.max_position_weight <= self.max_gross_exposure:
            raise ConfigurationError("need 0 < max_position_weight <= max_gross_exposure")


def apply_limits(targets: TargetWeights, limits: RiskLimits) -> dict[str, float]:
    """Clip per-position weights, drop shorts if disallowed, then scale to gross limit."""
    cap = limits.max_position_weight
    clipped: dict[str, float] = {}
    for symbol, weight in targets.items():
        allowed = weight if weight >= 0 or limits.allow_short else 0.0
        clipped[symbol] = max(-cap, min(cap, allowed))
    gross = sum(abs(w) for w in clipped.values())
    if gross > limits.max_gross_exposure:
        scale = limits.max_gross_exposure / gross
        clipped = {s: w * scale for s, w in clipped.items()}
    return clipped
