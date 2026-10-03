from datetime import date

import pytest

from algotrade.core.errors import AlgoTradeError
from algotrade.core.feature_view import FeatureView
from algotrade.engines.screening.runner import RunCoverage, run_screen
from algotrade.strategies.screeners.base import Decision, Screener, ScreenRow

DAY = date(2026, 10, 2)


class Fixed(Screener):
    name = "fixed"

    def __init__(
        self, decisions: dict[str, Decision], extra: list[ScreenRow] | None = None
    ) -> None:
        self.decisions = decisions
        self.extra = extra or []

    def screen(self, view: FeatureView) -> list[ScreenRow]:
        rows = [
            ScreenRow(i, self.decisions[i], reasons=("r",)) for i in view if i in self.decisions
        ]
        return rows + self.extra


def view(ids: list[str]) -> FeatureView:
    return FeatureView(DAY, {i: {} for i in ids})


def test_complete_run_with_audit() -> None:
    ids = [f"EQ:{i}" for i in range(100)]
    decisions = dict.fromkeys(ids, Decision.QUALIFIED) | {"EQ:0": Decision.UNKNOWN}
    run = run_screen(Fixed(decisions), view(ids), [*ids, "EQ:1"])
    assert run.coverage is RunCoverage.COMPLETE
    audit = run.audit()
    assert audit["duplicates_removed"] == 1
    assert audit["processed"] == 99
    assert audit["skipped_reasons"] == {"r": 1}
    assert run.counts() == {"UNKNOWN": 1, "QUALIFIED": 99}


def test_partial_when_coverage_low() -> None:
    ids = ["EQ:A", "EQ:B"]
    run = run_screen(Fixed({"EQ:A": Decision.UNKNOWN, "EQ:B": Decision.REJECT}), view(ids), ids)
    assert run.coverage is RunCoverage.PARTIAL
    assert run.coverage_pct == 0.5


def test_empty_universe_is_incomplete() -> None:
    run = run_screen(Fixed({}), view([]), [])
    assert run.coverage is RunCoverage.UNIVERSE_INCOMPLETE
    assert run.coverage_pct == 0.0


def test_screener_must_cover_universe_exactly_once() -> None:
    ids = ["EQ:A", "EQ:B"]
    with pytest.raises(AlgoTradeError, match="one row per"):
        run_screen(Fixed({"EQ:A": Decision.QUALIFIED}), view(ids), ids)
    dup = Fixed(
        {"EQ:A": Decision.QUALIFIED, "EQ:B": Decision.QUALIFIED},
        extra=[ScreenRow("EQ:A", Decision.REJECT)],
    )
    with pytest.raises(AlgoTradeError, match="twice"):
        run_screen(dup, view(ids), ids)
    with pytest.raises(AlgoTradeError, match="exactly the universe"):
        run_screen(Fixed({}), view(["EQ:A"]), ids)
