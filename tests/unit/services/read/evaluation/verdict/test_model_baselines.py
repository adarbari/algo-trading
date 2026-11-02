"""A named sleeve's baselines are per symbol (``position:<template>:<symbol>``): a candidate is
compared with its own symbol's, never another's (ADR 0088 G19)."""

from algotrade.services.read.evaluation.verdict.model import baselines_for
from tests.unit.services.read.evaluation.verdict.test_rule import row


def test_a_candidate_takes_its_own_symbols_baseline_and_every_cross_section_one() -> None:
    main = [
        row("position:long_shares:SPY", "baseline"),
        row("position:long_shares:QQQ", "baseline"),
        row("position:long_shares", "baseline"),
        row("momo", "baseline"),
        row("SPY"),
        row("position:long_shares:SPY", "baseline", "in_sample"),
    ]
    spy = baselines_for(main, "SPY", 20, "frozen")
    assert [r.variant for r in spy] == ["position:long_shares:SPY", "position:long_shares", "momo"]
    qqq = baselines_for(main, "QQQ", 20, "frozen")
    assert [r.variant for r in qqq] == ["position:long_shares:QQQ", "position:long_shares", "momo"]
    assert [r.slice_kind for r in baselines_for(main, "SPY", 20, "in_sample")] == ["in_sample"]
