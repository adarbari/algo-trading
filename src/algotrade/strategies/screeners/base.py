"""The screener contract and the shared decision categories."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from algotrade.core.views.feature_view import FeatureValue, FeatureView


class Decision(StrEnum):
    """Shared by every screener so the UI and audits treat them uniformly."""

    QUALIFIED = "QUALIFIED"
    WATCH = "WATCH"  # interesting, but one gate missed
    EVENT_RISK = "EVENT_RISK"
    LIQUIDITY_RISK = "LIQUIDITY_RISK"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"  # data missing or stale: fail closed, never counted as processed
    SKIPPED = "SKIPPED"  # a rule screen's gating criterion has no data (ADR 0029): not processed
    # A pick held back by the regime gate (ADR 0049), with its reason. Processed: the row was
    # decided on its data, so it never lowers coverage (a Storm run is not PARTIAL).
    PAUSED = "PAUSED"

    @property
    def processed(self) -> bool:
        """False for the fail-closed outcomes (UNKNOWN, SKIPPED): they lower coverage."""
        return self not in (Decision.UNKNOWN, Decision.SKIPPED)


@dataclass(frozen=True)
class ScreenRow:
    instrument_id: str
    decision: Decision
    score: float | None = None
    reasons: tuple[str, ...] = ()
    values: Mapping[str, FeatureValue] = field(default_factory=dict)


class Screener(ABC):
    name: str = "unnamed"
    # Feature tables this screener reads, e.g. ("rollups/instrument/option_liquidity@v1",)
    requires: tuple[str, ...] = ()

    @abstractmethod
    def screen(self, view: FeatureView) -> list[ScreenRow]:
        """Return exactly one row per instrument in ``view``."""

    def params(self) -> dict[str, float | int | str]:
        return {}
