"""Scale target weights by a market label (ADR 0049): ``ScaleByLabel``.

The regime overlay: every weight is multiplied by the multiplier of the session's label
(``market.regime@v3.label``: CALM 1.0, CAUTION 0.75, STRESS 0.5, CRISIS 0.25 by default). A
label in ``pause_in`` scales to 0. An unknown label (null, or a value with no multiplier) fails
closed: ``unknown_multiplier`` (0.0 by default), never the CALM multiplier. A name the session's
values do not carry at all is a ``MissingDataError`` (ADR 0008): the run did not load it.

Volatility targeting is the next overlay, ``ScaleByValue`` (a multiplier from a numeric market
value); it is not written yet.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from algotrade.core.model.errors import MissingDataError
from algotrade.core.model.types import TargetWeights
from algotrade.core.views.feature_view import FeatureValue
from algotrade.core.views.market_features import HINT, MARKET_FEATURES
from algotrade.engines.overlays.overlay import OverlayStep

UNKNOWN = "regime unknown"


@dataclass(frozen=True)
class ScaleByLabel:
    feature: str  # the label's market feature name
    multipliers: Mapping[str, float]  # label -> multiplier in [0, 1]
    pause_in: frozenset[str] = frozenset()  # labels that scale to 0
    unknown_multiplier: float = 0.0  # a null or unrecognised label (fail closed)

    def __post_init__(self) -> None:
        bad = [
            f"{label}={m}"
            for label, m in (*self.multipliers.items(), ("<unknown>", self.unknown_multiplier))
            if not 0.0 <= m <= 1.0
        ]
        if bad:
            raise ValueError(f"{self.feature}: multipliers must be in [0, 1], got {bad}")

    def multiplier(self, label: FeatureValue) -> tuple[float, str | None]:
        """``label``'s multiplier and the reason it is not 1 (``None`` when it is)."""
        if not isinstance(label, str) or label not in self.multipliers:
            return self.unknown_multiplier, UNKNOWN
        if label in self.pause_in:
            return 0.0, f"regime={label}: paused"
        value = float(self.multipliers[label])
        return value, None if value == 1.0 else f"regime={label}: x{value:g}"

    def apply(self, weights: TargetWeights, market: Mapping[str, FeatureValue]) -> OverlayStep:
        if self.feature not in market:
            raise MissingDataError(MARKET_FEATURES, f"{self.feature} is not loaded", HINT)
        factor, reason = self.multiplier(market[self.feature])
        if reason is None:
            return OverlayStep(dict(weights))
        return OverlayStep({i: w * factor for i, w in weights.items()}, (reason,))
