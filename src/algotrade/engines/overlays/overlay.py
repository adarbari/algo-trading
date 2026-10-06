"""The overlay contract (ADR 0049): target weights and the session's market values in, the
adjusted weights and why out.

The engine calls ``apply`` at the close of bar ``t`` with session ``t``'s market values
(``MarketFeatures.at(t)``), after the strategy's ``on_bar`` and before ``apply_limits``; the
orders it leads to fill at the open of ``t + 1``. An overlay is deterministic, never reads
anything but its arguments, and names a reason for every change it makes.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from algotrade.core.model.types import TargetWeights
from algotrade.core.views.feature_view import FeatureValue


@dataclass(frozen=True)
class OverlayStep:
    """An overlay's output: the weights to carry on with and the reasons they changed (empty
    when they did not)."""

    weights: TargetWeights
    reasons: tuple[str, ...] = ()


class Overlay(Protocol):
    def apply(self, weights: TargetWeights, market: Mapping[str, FeatureValue]) -> OverlayStep: ...
