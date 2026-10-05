from collections.abc import Sequence

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.screens.results import (
    ChangeCount,
    CriterionResult,
    ResultColumn,
    ResultPage,
    ResultQuery,
    RunChanges,
    load_result_page,
    load_results,
    load_run_changes,
)
from algotrade.services.read.screens.runs import latest_run
from tests.unit.services.read.screens.conftest import D0


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
    assert (aaa.change, aaa.previous_decision) == (None, None)  # not compared


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


def test_changes_against_the_previous_run(ctx: ReadContext) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    changes = load_run_changes(ctx, run)
    assert changes.previous_session == D0
    assert changes.counts == (ChangeCount("new", 1), ChangeCount("dropped", 1))
    # AAA: REJECT then QUALIFIED (new); BBB: QUALIFIED then WATCH (still picked); CCC: dropped
    assert dict(changes.by_instrument) == {
        "EQ:AAA": ("new", "REJECT"), "EQ:BBB": (None, "QUALIFIED"),
        "EQ:CCC": ("dropped", "QUALIFIED"),
    }  # fmt: skip
    assert load_run_changes(ctx, run) is changes  # cached per run and published state
    beta = latest_run(ctx, "me", "beta").run
    assert beta is not None
    assert load_run_changes(ctx, beta) == RunChanges(None, (), {})


def _page(
    ctx: ReadContext,
    query: ResultQuery | None = None,
    columns: Sequence[str] = (),
    page: int = 1,
    size: int = 100,
) -> ResultPage:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    return load_result_page(ctx, run, query, columns, page, size)


def _symbols(page: ResultPage) -> list[str | None]:
    return [r.instrument.symbol if r.instrument else None for r in page.results]


def _sorted(ctx: ReadContext, sort: str) -> list[str | None]:
    return _symbols(_page(ctx, ResultQuery(sort=sort)))


def test_a_page_of_the_run_by_rank_with_its_changes(ctx: ReadContext) -> None:
    found = _page(ctx)
    assert (found.run_id, found.sort, found.total, found.page, found.size) == (
        "r1", "rank", 3, 1, 100
    )  # fmt: skip
    assert _symbols(found) == ["AAA", "BBB", "CCC"]
    assert [(r.change, r.previous_decision) for r in found.results] == [
        ("new", "REJECT"), (None, "QUALIFIED"), ("dropped", "QUALIFIED")
    ]  # fmt: skip
    assert (found.columns, found.missing) == ((), ())
    assert found.rows == found.unknown == ((), (), ())


def test_filters_and_search(ctx: ReadContext) -> None:
    assert _symbols(_page(ctx, ResultQuery(decisions=("qualified", "WATCH")))) == ["AAA", "BBB"]
    assert _symbols(_page(ctx, ResultQuery(change="dropped"))) == ["CCC"]
    assert _symbols(_page(ctx, ResultQuery(q=" bb "))) == ["BBB"]
    second = _page(ctx, page=2, size=2)
    assert (second.total, _symbols(second)) == (3, ["CCC"])


def test_sorts_put_missing_values_last(ctx: ReadContext) -> None:
    assert _sorted(ctx, "-score") == ["BBB", "AAA", "CCC"]
    assert _sorted(ctx, "-rank") == ["CCC", "BBB", "AAA"]
    assert _sorted(ctx, "symbol") == ["AAA", "BBB", "CCC"]
    assert _sorted(ctx, "decision") == ["AAA", "CCC", "BBB"]
    assert _sorted(ctx, "change") == ["CCC", "AAA", "BBB"]  # dropped, new, then none
    # Only BBB stored iv_rank, only AAA iv30 (text) and the column: the others go last.
    assert _sorted(ctx, "-criterion:iv_rank")[0] == "BBB"
    assert _sorted(ctx, "-criterion:iv30")[0] == "AAA"
    assert _sorted(ctx, "column:spread")[0] == "AAA"


def test_catalogue_columns_and_a_catalogue_sort(ctx: ReadContext) -> None:
    found = _page(ctx, ResultQuery(sort="-instrument.symbol"), ["instrument.symbol"] * 2)
    assert [c.name for c in found.columns] == ["instrument.symbol"]
    assert _symbols(found) == ["CCC", "BBB", "AAA"]
    assert found.rows == (("CCC",), ("BBB",), ("AAA",))
    assert found.unknown == ((None,), (None,), (None,))


def test_bad_queries_name_the_problem(ctx: ReadContext) -> None:
    with pytest.raises(ConfigurationError, match="change"):
        _page(ctx, ResultQuery(change="gone"))
    with pytest.raises(ConfigurationError, match="names no criterion"):
        _page(ctx, ResultQuery(sort="criterion:"))
    with pytest.raises(UnknownFeatureError):
        _page(ctx, ResultQuery(sort="nope"))
    with pytest.raises(UnknownFeatureError):
        _page(ctx, columns=["feature.no_such"])
