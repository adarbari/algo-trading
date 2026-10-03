"""The screener contract and the shared decision categories."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from algotrade.core.feature_view import FeatureValue, FeatureView


class Decision(StrEnum):
    """Shared by every screener so the UI and audits treat them uniformly."""

    QUALIFIED = "QUALIFIED"
    WATCH = "WATCH"  # interesting, but one gate missed
    EVENT_RISK = "EVENT_RISK"
    LIQUIDITY_RISK = "LIQUIDITY_RISK"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"  # data missing or stale: fail closed, never counted as processed


@dataclass(frozen=True)
class ScreenRow:
    instrument_id: str
    decision: Decision
    score: float | None = None
    reasons: tuple[str, ...] = ()
    values: Mapping[str, FeatureValue] = field(default_factory=dict)


class Screener(ABC):
    name: str = "unnamed"
    # Feature tables this screener reads, e.g. ("features/option_liquidity@v1",)
    requires: tuple[str, ...] = ()

    @abstractmethod
    def screen(self, view: FeatureView) -> list[ScreenRow]:
        """Return exactly one row per instrument in ``view``."""

    def params(self) -> dict[str, float | int | str]:
        return {}
