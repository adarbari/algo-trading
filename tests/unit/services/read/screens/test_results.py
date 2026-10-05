from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens.results import CriterionResult, ResultColumn, load_results
from algotrade.services.read.screens.runs import latest_run


def test_results_carry_criteria_columns_flags_and_identity(ctx: ReadContext) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    found = load_results(ctx, {"r1": ["EQ:AAA", "EQ:BBB", "EQ:ZZZ"]}, [run])
    assert sorted(found) == [("r1", "EQ:AAA"), ("r1", "EQ:BBB")]  # no row for ZZZ
    aaa, bbb = found[("r1", "EQ:AAA")], found[("r1", "EQ:BBB")]
    assert aaa.instrument is not None and aaa.instrument.symbol == "AAA"
    assert (aaa.rank, aaa.decision, aaa.score, aaa.flags) == (1, "QUALIFIED", 50.0, ())
    assert aaa.columns == (ResultColumn("spread", 0.05),)
    assert aaa.criteria == (CriterionResult("iv30", "feature.vrp_iv30", "hard", "PASS", "high",
                                            None),)  # fmt: skip
    assert (bbb.tie_break, bbb.flags) == (2.0, ("large_move",))
    assert bbb.criteria == (
        CriterionResult("iv_rank", "rollup.x@v1.iv_rank", "soft", "NEAR", 40.0, 10.0),
    )


def test_nothing_asked_reads_nothing(ctx: ReadContext) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    assert load_results(ctx, {"r1": []}, [run]) == {}
    assert load_results(ctx, {"other": ["EQ:AAA"]}, [run]) == {}


def test_a_run_with_no_stored_values(ctx: ReadContext) -> None:
    run = latest_run(ctx, "me", "beta").run
    assert run is not None
    found = load_results(ctx, {"rb": ["EQ:DDD"]}, [run])[("rb", "EQ:DDD")]
    assert (found.criteria, found.columns, found.score) == ((), (), 10.0)
