"""``EvidenceProgress``: the verdict's trade counts against what it needs, and its checks."""

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.services.read.evaluation.evidence import evidence_of
from tests.unit.services.read.evaluation.verdict.test_judge import result, verdict

T = VerdictSettings()


def test_the_meter_is_the_oos_count_against_the_minimum_and_the_works_counts() -> None:
    ev = verdict(result(oos={"sessions": 12}, whole={"sessions": 70})).evidence
    assert ev is not None
    assert (ev.oos_trades, ev.needed, ev.works_oos_needed) == (
        12,
        T.min_oos_trades,
        T.works_oos_trades,
    )
    assert (ev.whole_trades, ev.whole_needed) == (70, T.works_trades)
    assert not ev.reached


def test_reached_at_the_minimum() -> None:
    at = verdict(result(oos={"sessions": T.min_oos_trades})).evidence
    below = verdict(result(oos={"sessions": T.min_oos_trades - 1})).evidence
    assert at is not None and below is not None
    assert at.reached and not below.reached


def test_checks_are_the_verdicts_criteria_in_the_meters_order() -> None:
    v = verdict(result())
    assert v.evidence is not None
    ids = [c.id for c in v.evidence.checks]
    assert ids == ["win_rate", "random", "baselines", "trades"]
    by = {c.id: c for c in v.criteria}
    assert all(c == by[c.id] for c in v.evidence.checks)


def test_a_missing_criterion_is_skipped_and_none_counts_are_zero() -> None:
    ev = evidence_of(None, None, [], T)
    assert (ev.oos_trades, ev.whole_trades, ev.reached, ev.checks) == (0, 0, False, ())
