"""The regime gate (ADR 0049): picks PAUSED in the screener's regimes or when the label is
unknown, every other decision untouched, coverage unchanged."""

from datetime import date

import pytest

from algotrade.core.views.feature_view import FeatureView
from algotrade.engines.screening.gate import UNKNOWN, RegimeGate, gate_rows
from algotrade.engines.screening.runner import RunCoverage, ScreenRun, run_screen
from algotrade.strategies.screeners.base import Decision, Screener, ScreenRow

DAY = date(2026, 10, 2)
MULTIPLIERS = {"CALM": 1.0, "CAUTION": 0.75, "STRESS": 0.5, "CRISIS": 0.25}
DECISIONS = {
    "EQ:A": Decision.QUALIFIED,
    "EQ:B": Decision.WATCH,
    "EQ:C": Decision.REJECT,
    "EQ:D": Decision.UNKNOWN,
    "EQ:E": Decision.EVENT_RISK,
}


class Fixed(Screener):
    name = "vrp"

    def screen(self, view: FeatureView) -> list[ScreenRow]:
        return [ScreenRow(i, DECISIONS[i], 1.0, ("own",)) for i in view]


def gate(label: object, pause_in: frozenset[str] = frozenset({"STRESS", "CRISIS"})) -> RegimeGate:
    return RegimeGate("vrp_scanner", label, MULTIPLIERS, pause_in)  # type: ignore[arg-type]


def run(g: RegimeGate | None) -> ScreenRun:
    ids = sorted(DECISIONS)
    return run_screen(Fixed(), FeatureView(DAY, {i: {} for i in ids}), ids, 0.5, g)


def test_a_paused_regime_pauses_only_the_picks_and_keeps_coverage() -> None:
    plain, paused = run(None), run(gate("STRESS"))
    by_id = {r.instrument_id: r for r in paused.rows}
    reason = "regime=STRESS: vrp_scanner pauses in STRESS"
    assert by_id["EQ:A"].decision is Decision.PAUSED and by_id["EQ:A"].reasons == (reason, "own")
    assert by_id["EQ:B"].decision is Decision.PAUSED
    assert [by_id[i].decision for i in ("EQ:C", "EQ:D", "EQ:E")] == [
        Decision.REJECT,
        Decision.UNKNOWN,
        Decision.EVENT_RISK,
    ]
    assert by_id["EQ:A"].score == 1.0  # the row is kept whole, never dropped
    assert paused.processed == plain.processed == 4 and paused.coverage is RunCoverage.COMPLETE
    assert paused.counts()["PAUSED"] == 2 and "PAUSED" not in paused.skipped_reasons()
    assert Decision.PAUSED.processed


@pytest.mark.parametrize("label", [None, "STORM", 2.0])
def test_an_unknown_regime_pauses_every_pick(label: object) -> None:
    g = gate(label, frozenset())
    assert g.reason == UNKNOWN and g.size_multiplier == 0.0
    rows = gate_rows(Fixed().screen(FeatureView(DAY, {"EQ:A": {}, "EQ:C": {}})), g)
    assert [(r.decision, r.reasons[0]) for r in rows] == [
        (Decision.PAUSED, UNKNOWN),
        (Decision.REJECT, "own"),
    ]


@pytest.mark.parametrize(
    ("label", "regime", "size", "reason"),
    [
        ("CALM", "CALM", 1.0, None),
        ("CAUTION", "CAUTION", 0.75, None),
        ("STRESS", "STRESS", 0.0, "regime=STRESS: vrp_scanner pauses in STRESS"),
        (None, None, 0.0, UNKNOWN),
    ],
)
def test_the_runs_regime_and_size(
    label: str | None, regime: str | None, size: float, reason: str | None
) -> None:
    g = gate(label)
    assert (g.regime, g.size_multiplier, g.reason) == (regime, size, reason)


def test_a_regime_the_screener_does_not_pause_in_lets_rows_through() -> None:
    assert run(gate("CAUTION")).rows == run(None).rows
    assert run(gate("STRESS", frozenset())).counts() == run(None).counts()
    assert run(gate("STRESS")).rows == run(gate("STRESS")).rows  # deterministic
