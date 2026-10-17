from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.screens import results, runs
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
    run_withheld,
)
from algotrade.services.read.screens.runs import ScreenerRun, latest_run
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.screens.conftest import D0, D1, T, context, write_gated, write_run


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


def test_only_the_asked_instruments_values_become_records(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    # every run's value rows of every asked instrument were turned into records, though a run
    # is only read back for its own: most of an Ideas read on the real store
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    converted: list[int] = []
    real = results._records

    def counting(frame: pd.DataFrame) -> list[Any]:
        converted.append(len(frame))
        return real(frame)

    monkeypatch.setattr(results, "_records", counting)
    both = load_results(ctx, {"r1": ["EQ:AAA", "EQ:BBB"]}, [run])
    converted.clear()
    one = load_results(ctx, {"r1": ["EQ:AAA"]}, [run])
    assert sorted(both) == [("r1", "EQ:AAA"), ("r1", "EQ:BBB")] and sorted(one) == [
        ("r1", "EQ:AAA")
    ]
    assert converted == [2, 1]  # AAA's two value rows and its result row, not BBB's
    assert one[("r1", "EQ:AAA")] == both[("r1", "EQ:AAA")]


def test_the_value_rows_of_a_page_are_read_once_per_published_state(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the Ideas page read the session's 4.9 million value rows on every load (0.75 s)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    read: list[str] = []
    real = results.partition

    def counting(c: ReadContext, table: str, *args: Any) -> Any:
        read.append(table)
        return real(c, table, *args)

    monkeypatch.setattr(results, "partition", counting)
    first = load_results(ctx, {"r1": ["EQ:AAA"]}, [run])
    assert load_results(replace(ctx, memo={}), {"r1": ["EQ:AAA"]}, [run]) == first
    assert len(read) == 1  # another request, the same answer, nothing read
    load_results(ctx, {"r1": ["EQ:AAA", "EQ:BBB"]}, [run])
    assert len(read) == 2  # other instruments: read
    seq = ctx.reader.visible_seq()
    monkeypatch.setattr(ctx.reader, "visible_seq", lambda: seq + 1)  # a publish
    load_results(ctx, {"r1": ["EQ:AAA"]}, [run])
    assert len(read) == 3


def test_a_runs_rows_are_filtered_once_per_request(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    filtered: list[str] = []
    real = runs.screen_rows

    def counting(c: ReadContext) -> Any:
        filtered.append(c.session.date.isoformat())
        return real(c)

    monkeypatch.setattr(runs, "screen_rows", counting)
    first = runs.run_rows(ctx, run)
    assert runs.run_rows(ctx, run) is first and len(filtered) == 1
    assert runs.run_rows(replace(ctx, memo={}), run) is not first  # another request: its own


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


def test_a_paused_row_carries_its_reason_the_label_and_the_size(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    ctx = context(reader)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None and run.run_id == "r2"
    found = load_results(ctx, {"r2": ["EQ:AAA", "EQ:BBB"]}, [run])
    aaa, bbb = found[("r2", "EQ:AAA")], found[("r2", "EQ:BBB")]
    assert (bbb.decision, bbb.reasons) == ("PAUSED", "regime=STRESS: alpha")
    assert (bbb.regime, bbb.size_multiplier) == ("STRESS", 0.5)
    assert (aaa.regime, aaa.size_multiplier) == ("STRESS", 0.5)


def test_a_run_before_the_stamp_has_no_regime_on_its_rows(ctx: ReadContext) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    row = load_results(ctx, {"r1": ["EQ:AAA"]}, [run])[("r1", "EQ:AAA")]
    assert (row.regime, row.size_multiplier) == (None, None)


def test_a_paused_pick_is_dropped_against_the_previous_run_and_filters_by_decision(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    ctx = context(reader)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    assert load_run_changes(ctx, run).by_instrument["EQ:BBB"] == ("dropped", "QUALIFIED")
    page = load_result_page(ctx, run, ResultQuery(decisions=("paused",)))
    assert page.total == 2
    assert [(r.instrument_id, r.decision) for r in page.results] == [
        ("EQ:BBB", "PAUSED"), ("EQ:DDD", "PAUSED")
    ]  # fmt: skip


def test_a_run_the_viewer_may_see_only_by_names_and_decisions_serves_no_value_score_or_reasons(
    reader: StoreReader,
) -> None:
    """Fix for: a run recorded under a licence the viewer lacks (the scheduled site run holds
    every licence) served its stored values, score, tie-break and ``reasons`` (which embed the
    value: "0.83, needs >= 0.9") to any viewer. The viewer sees names and decisions, as the
    ledger does (ADR 0064 decision 10, ADR 0069); the run recorded ``vrp_iv30`` and ``iv_rank``
    as personal and ``spread`` as open; a sort by rank or score is by symbol."""
    trader = context(reader, user="trader")
    run = latest_run(trader, "site", "alpha").run
    assert run is not None
    found = load_results(trader, {"r1": ["EQ:AAA", "EQ:BBB"]}, [run])
    aaa, bbb = found[("r1", "EQ:AAA")], found[("r1", "EQ:BBB")]
    assert aaa.decision == "QUALIFIED" and bbb.instrument is not None  # names and decisions
    assert (aaa.score, aaa.tie_break, aaa.reasons) == (None, None, "")
    assert aaa.rank is None and bbb.rank is None  # the order follows the hidden score
    assert (bbb.score, bbb.tie_break, bbb.reasons) == (None, None, "")
    assert aaa.criteria == (
        CriterionResult("iv30", "feature.vrp_iv30", "hard", "MISSING", None, None),
    )
    assert aaa.columns == (ResultColumn("spread", 0.05),)  # recorded open: visible
    assert bbb.criteria[0].value is None and bbb.criteria[0].outcome == "MISSING"
    assert _sorted(trader, "-score") == ["CCC", "BBB", "AAA"]  # by symbol, not by score
    assert run_withheld(trader, run) != frozenset()

    holder = context(reader)  # ``me`` holds the licence
    assert run_withheld(holder, run) == frozenset()
    seen = load_results(holder, {"r1": ["EQ:AAA"]}, [run])[("r1", "EQ:AAA")]
    assert seen.criteria[0].value == "high" and seen.score == 50.0 and seen.rank == 1


OPEN_FIELD = "rollup.price_stats@v2.close"  # open in every catalogue


def _later_run(
    backend: MemoryBackend,
    reader: StoreReader,
    user: str,
    recorded: dict[str, str] | None,
    field_name: str,
    docs: Any = None,
) -> tuple[ReadContext, ScreenerRun]:
    """``user``'s context and the latest ``alpha`` run, ``r3``: one stored criterion on
    ``field_name`` (value 7.0, PASS) and ``recorded`` as the licences its record holds (None: a
    record without them)."""
    writer = StoreWriter(backend)
    later = T + timedelta(hours=3)
    write_run(writer, D1, "r3", "site", "alpha", [("AAA", "QUALIFIED", 50.0, None)], later)
    row = {"instrument_id": "EQ:AAA", "user_id": "site", "config_id": "alpha",
           "criterion_id": "shared", "field": field_name, "mode": "hard", "value_num": 7.0,
           "value_str": None, "outcome": "PASS", "distance": None}  # fmt: skip
    writer.write_result("rule_screen_values", D1, "r3", stamped([row], D1, "r3", later))
    stats = {} if recorded is None else {"field_licences": recorded}
    writer.save_run(RunRecord("r3", "screen-alpha-site", D1, later).finish(later, stats=stats))
    ctx = context(reader, docs, user=user)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None and run.run_id == "r3"
    return ctx, run


def test_a_viewers_same_named_open_expression_does_not_open_a_stored_personal_value(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """Fix for: ``run_withheld`` resolved each stored field NAME in the VIEWER's catalogue, so a
    viewer's own open expression named like a field the run's owner computed from a personal
    source passed as ``open`` and exposed the stored value, score and reasons (ADR 0069: the
    recorded licence, never the name)."""
    mine = {"shared": {"expr": "price_stats.close", "dtype": "float", "unit": "usd",
                       "description": "d", "null_meaning": "n"}}  # fmt: skip
    trader, run = _later_run(
        backend, reader, "trader", {"feature.shared": "personal"}, "feature.shared",
        {("trader", "features", "mine"): mine},
    )  # fmt: skip
    found = trader.features.feature("feature.shared")
    assert found is not None and found.licence == "open"  # the viewer's own: open by name
    assert run_withheld(trader, run) == {"feature.shared"}
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert seen.criteria[0].value is None and seen.criteria[0].outcome == "MISSING"
    assert (seen.score, seen.rank, seen.reasons) == (None, None, "")


@pytest.mark.parametrize("recorded", [None, {}, {"feature.other": "open"}])
def test_a_stored_field_with_no_recorded_licence_is_hidden(
    backend: MemoryBackend, reader: StoreReader, recorded: dict[str, str] | None
) -> None:
    """A run whose record has no licences (before the record), or lacks the field, withholds
    it even when the viewer's catalogue resolves the name as open (fail closed)."""
    trader, run = _later_run(backend, reader, "trader", recorded, OPEN_FIELD)
    assert run_withheld(trader, run) == {OPEN_FIELD}
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert seen.criteria[0].value is None and seen.score is None


def test_a_recorded_open_field_is_visible_to_every_viewer(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    trader, run = _later_run(backend, reader, "trader", {OPEN_FIELD: "open"}, OPEN_FIELD)
    assert run_withheld(trader, run) == frozenset()
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert (seen.criteria[0].value, seen.score, seen.rank) == (7.0, 50.0, 1)


@pytest.mark.parametrize("recorded", [None, {OPEN_FIELD: "personal"}])
def test_the_holder_of_every_licence_sees_a_run_whatever_it_recorded(
    backend: MemoryBackend, reader: StoreReader, recorded: dict[str, str] | None
) -> None:
    holder, run = _later_run(backend, reader, "me", recorded, OPEN_FIELD)
    assert run_withheld(holder, run) == frozenset()
    seen = load_results(holder, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert (seen.criteria[0].value, seen.score, seen.rank) == (7.0, 50.0, 1)
