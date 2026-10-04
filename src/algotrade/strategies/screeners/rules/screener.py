"""``RuleScreener``: a rule screen (``impl = "rules"``) under the shared ``Screener`` contract,
so it registers and runs like any screener. Its spec comes from the resolved config."""

from algotrade.core.model.screen_spec import ScreenSpec
from algotrade.core.views.feature_view import FeatureView
from algotrade.strategies.screeners.base import Screener, ScreenRow
from algotrade.strategies.screeners.rules.evaluate import (
    RuleScreenResult,
    ScreenMemo,
    evaluate_screen,
)

RULES = "rules"


class RuleScreener(Screener):
    name = RULES

    def __init__(self, spec: ScreenSpec) -> None:
        self.spec = spec

    def evaluate(self, view: FeatureView, memo: ScreenMemo | None = None) -> RuleScreenResult:
        """The full result: ranked rows with criterion detail and the run summary (``memo``:
        the preview's criterion results over this view; the rows are the same without)."""
        return evaluate_screen(self.spec, view, memo)

    def screen(self, view: FeatureView) -> list[ScreenRow]:
        return [row.screen_row() for row in self.evaluate(view).rows]

    def params(self) -> dict[str, float | int | str]:
        return {"spec": self.spec.id, "version": self.spec.version or 0}
