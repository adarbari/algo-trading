"""The exclusion step (ADR 0054): a not-processed row of an excluded name becomes EXCLUDED with
the reason first; a decided row is never rewritten; EXCLUDED is out of the coverage denominator."""

from datetime import date

from algotrade.core.views.feature_view import FeatureView
from algotrade.engines.screening.exclusions import exclude_rows, exclude_rule_result
from algotrade.engines.screening.runner import RunCoverage, run_screen
from algotrade.strategies.screeners.base import Decision, Screener, ScreenRow
from algotrade.strategies.screeners.rules import RuleScreenResult
from algotrade.strategies.screeners.rules.row import RuleRow
from algotrade.strategies.screeners.rules.summary import summarise

DAY = date(2026, 10, 2)
WHY = "stale chain"
DECISIONS = {
    "EQ:A": Decision.QUALIFIED,
    "EQ:B": Decision.UNKNOWN,
    "EQ:C": Decision.SKIPPED,
    "EQ:D": Decision.PAUSED,
    "EQ:E": Decision.UNKNOWN,
}
EXCLUDED = {"EQ:A": WHY, "EQ:B": WHY, "EQ:C": WHY, "EQ:D": WHY}  # E is not excluded


class Fixed(Screener):
    name = "fixed"

    def screen(self, view: FeatureView) -> list[ScreenRow]:
        return [ScreenRow(i, DECISIONS[i], 1.0, ("own",)) for i in view]


def test_only_not_processed_rows_of_excluded_names_are_rewritten_reason_first() -> None:
    rows = [ScreenRow(i, d, 1.0, ("own",)) for i, d in DECISIONS.items()]
    out = {r.instrument_id: r for r in exclude_rows(rows, EXCLUDED)}
    assert {i: r.decision for i, r in out.items()} == {
        "EQ:A": Decision.QUALIFIED,  # decided: left alone
        "EQ:B": Decision.EXCLUDED,
        "EQ:C": Decision.EXCLUDED,
        "EQ:D": Decision.PAUSED,
        "EQ:E": Decision.UNKNOWN,  # not in the map
    }
    assert out["EQ:B"].reasons == (WHY, "own")
    assert out["EQ:B"].score == 1.0
    assert exclude_rows(rows, {}) == rows


def run(excluded: dict[str, str] | None):
    ids = sorted(DECISIONS)
    return run_screen(Fixed(), FeatureView(DAY, {i: {} for i in ids}), ids, 0.5, None, excluded)


def test_excluded_rows_leave_the_coverage_denominator() -> None:
    plain, excluded = run(None), run(EXCLUDED)
    assert (plain.processed, plain.coverage_pct) == (2, 0.4)  # A and D of 5
    assert plain.coverage is RunCoverage.PARTIAL
    assert (excluded.excluded, excluded.processed) == (2, 2)
    assert excluded.coverage_pct == 2 / 3  # E still lowers it: it is not excluded
    audit = excluded.audit()
    assert (audit["excluded"], audit["skipped"]) == (2, 1)
    assert audit["excluded_reasons"] == {WHY: 2}
    assert audit["skipped_reasons"] == {"own": 1}


def test_a_run_of_only_excluded_names_has_no_coverage() -> None:
    ids = ["EQ:B", "EQ:C"]
    out = run_screen(
        Fixed(), FeatureView(DAY, {i: {} for i in ids}), ids, 0.5, None, dict.fromkeys(ids, WHY)
    )
    assert (out.excluded, out.coverage_pct) == (2, 0.0)
    assert out.coverage is RunCoverage.PARTIAL  # nothing left to cover: never a clean run


def test_a_rule_result_keeps_its_ranks_and_recounts_its_summary() -> None:
    def row(i: str, decision: Decision, rank: int) -> RuleRow:
        return RuleRow(i, decision, 1.0, rank, ("no field",), ())

    rows = (row("EQ:A", Decision.QUALIFIED, 1), row("EQ:B", Decision.SKIPPED, 2))
    result = RuleScreenResult(None, rows, summarise(rows))  # type: ignore[arg-type]
    out = exclude_rule_result(result, {"EQ:A": WHY, "EQ:B": WHY})
    assert [(r.instrument_id, r.decision, r.rank) for r in out.rows] == [
        ("EQ:A", Decision.QUALIFIED, 1),
        ("EQ:B", Decision.EXCLUDED, 2),
    ]
    assert out.rows[1].reasons == (WHY, "no field")
    assert out.summary.decisions == (("EXCLUDED", 1), ("QUALIFIED", 1))
    assert exclude_rule_result(result, {}) is result
