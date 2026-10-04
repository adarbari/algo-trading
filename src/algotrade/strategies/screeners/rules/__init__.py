"""The rule screener (ADR 0029, 0030): criteria (HARD / SOFT tolerance band / SCORE), the
decision (missing data never passes and never skips), distance-from-threshold score, flags /
columns and the run summary. Pure: reads only a ``FeatureView`` and a ``ScreenSpec``."""

from algotrade.strategies.screeners.rules.criteria import CriterionResult, Outcome
from algotrade.strategies.screeners.rules.evaluate import RuleScreenResult, evaluate_screen
from algotrade.strategies.screeners.rules.row import RuleRow
from algotrade.strategies.screeners.rules.screener import RULES, RuleScreener
from algotrade.strategies.screeners.rules.summary import NarrowMiss, RunSummary

__all__ = [
    "RULES",
    "CriterionResult",
    "NarrowMiss",
    "Outcome",
    "RuleRow",
    "RuleScreenResult",
    "RuleScreener",
    "RunSummary",
    "evaluate_screen",
]
