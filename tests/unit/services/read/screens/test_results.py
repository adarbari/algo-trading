from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.document import QUALITY_BAR
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.evaluation.edge_picks.frame import RESULT, edge_picks_frame
from algotrade.services.evaluation.edge_picks.night import (
    NOT_DECISION_DAY,
    PICKED,
    SKIPPED,
    EdgePicks,
)
from algotrade.services.features import catalogue
from algotrade.services.licences import hidden_stored
from algotrade.services.read.context import ReadContext, at_session
from algotrade.services.read.evaluation.pick_edges import (
    COUNTS,
    NOT_A_DECISION_DAY,
    NOT_COUNTED,
    NOT_STORED,
    PAUSED,
    UNJUDGED,
    PickEdge,
)
from algotrade.services.read.filtering.definitions import FilterRefusedError
from algotrade.services.read.filtering.masks import FilterInput, WindowUnit, Within
from algotrade.services.read.filtering.served import load_served_filters
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
    run_audit,
    run_withheld,
)
from algotrade.services.read.screens.runs import ScreenerRun, latest_run
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.screens.conftest import (
    D0,
    D1,
    RESULTS_FILTERS,
    Docs,
    T,
    context,
    write_gated,
    write_run,
)
from tests.unit.services.read.screens.test_ideas import DOCS, IV_FILTER, filter_store


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
    real = results.run_rows_of

    def counting(c: ReadContext, table: str, *args: Any, **kwargs: Any) -> Any:
        read.append(table)
        return real(c, table, *args, **kwargs)

    monkeypatch.setattr(results, "run_rows_of", counting)
    first = load_results(ctx, {"r1": ["EQ:AAA"]}, [run])
    assert load_results(replace(ctx, memo={}), {"r1": ["EQ:AAA"]}, [run]) == first
    assert len(read) == 1  # another request, the same answer, nothing read
    load_results(ctx, {"r1": ["EQ:AAA", "EQ:BBB"]}, [run])
    assert len(read) == 2  # other instruments: read
    seq = ctx.reader.visible_seq()
    monkeypatch.setattr(ctx.reader, "visible_seq", lambda: seq + 1)  # a publish
    load_results(ctx, {"r1": ["EQ:AAA"]}, [run])
    assert len(read) == 3


def test_a_runs_rows_are_read_once_per_publish_for_every_request(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    read: list[str] = []
    real = runs.run_rows_of

    def counting(c: ReadContext, table: str, run_id: str, *args: Any) -> Any:
        read.append(run_id)
        return real(c, table, run_id, *args)

    monkeypatch.setattr(runs, "run_rows_of", counting)
    first = runs.run_rows(ctx, run)
    assert runs.run_rows(ctx, run) is first and read == ["r1"]
    assert runs.run_rows(replace(ctx, memo={}), run) is first  # another request: the same rows
    seq = ctx.reader.visible_seq()
    monkeypatch.setattr(ctx.reader, "visible_seq", lambda: seq + 1)  # a publish
    assert runs.run_rows(ctx, run) is not first and read == ["r1", "r1"]


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
        "EQ:AAA": ("new", "REJECT", 2), "EQ:BBB": (None, "QUALIFIED", -1),
        "EQ:CCC": ("dropped", "QUALIFIED", -1),
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
    assert load_run_changes(ctx, run).by_instrument["EQ:BBB"] == ("dropped", "QUALIFIED", -1)
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


OPEN_FIELD = "rollup.price_stats@v2.close"  # open in the site catalogue
PERSONAL_FIELD = "feature.vrp_iv30"  # personal in the site catalogue (IBKR-derived)
OWN_FIELD = "feature.owners_own"  # a run owner's own expression: the site does not resolve it


def _later_run(
    backend: MemoryBackend,
    reader: StoreReader,
    user: str,
    recorded: dict[str, str] | None,
    field_name: str,
    docs: Any = None,
    *,
    values: bool = True,
    audit: dict[str, Any] | None = None,
) -> tuple[ReadContext, ScreenerRun]:
    """``user``'s context and the latest ``alpha`` run, ``r3``: one stored criterion on
    ``field_name`` (value 7.0, PASS; none when ``values`` is false) and ``recorded`` as the
    licences its record holds (None: a record without them), ``audit`` the rest of the record."""
    writer = StoreWriter(backend)
    later = T + timedelta(hours=3)
    write_run(writer, D1, "r3", "site", "alpha", [("AAA", "QUALIFIED", 50.0, None)], later)
    row = {"instrument_id": "EQ:AAA", "user_id": "site", "config_id": "alpha",
           "criterion_id": "shared", "field": field_name, "mode": "hard", "value_num": 7.0,
           "value_str": None, "outcome": "PASS", "distance": None}  # fmt: skip
    if values:
        writer.write_result("rule_screen_values", D1, "r3", stamped([row], D1, "r3", later))
    stats = {**(audit or {}), **({} if recorded is None else {"field_licences": recorded})}
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
    mine = {"owners_own": {"expr": "price_stats.close", "dtype": "float", "unit": "usd",
                           "description": "d", "null_meaning": "n"}}  # fmt: skip
    trader, run = _later_run(
        backend, reader, "trader", {OWN_FIELD: "personal"}, OWN_FIELD,
        {("trader", "features", "mine"): mine},
    )  # fmt: skip
    found = trader.features.feature(OWN_FIELD)
    assert found is not None and found.licence == "open"  # the viewer's own: open by name
    assert run_withheld(trader, run) == {OWN_FIELD}
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert seen.criteria[0].value is None and seen.criteria[0].outcome == "MISSING"
    assert (seen.score, seen.rank, seen.reasons) == (None, None, "")


@pytest.mark.parametrize("recorded", [None, {}])
def test_a_stored_field_with_no_recorded_licence_is_hidden(
    backend: MemoryBackend, reader: StoreReader, recorded: dict[str, str] | None
) -> None:
    """A run whose record has no licence for a field the site catalogue does not resolve
    withholds it, even when the viewer's catalogue would call the name open (fail closed)."""
    trader, run = _later_run(backend, reader, "trader", recorded, OWN_FIELD)
    assert run_withheld(trader, run) == {OWN_FIELD}
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


def test_a_field_the_run_read_but_stored_no_value_for_still_withholds_the_score(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """Fix for: the gate looked only at the criteria and columns in the values table, so a run
    whose only personal field was its tie-break (or a flag) still served the tie-break and the
    rank order; the run records every field its spec reads."""
    recorded = {OPEN_FIELD: "open", PERSONAL_FIELD: "personal"}  # the tie-break is personal
    trader, run = _later_run(backend, reader, "trader", recorded, OPEN_FIELD)
    assert run_withheld(trader, run) == {PERSONAL_FIELD}
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert (seen.score, seen.tie_break, seen.rank, seen.reasons) == (None, None, None, "")
    assert seen.criteria[0].value == 7.0  # the open criterion stays


def test_a_run_with_rows_but_no_readable_values_and_no_record_is_withheld_whole(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """The gate used to fail open when the values table held nothing for the run."""
    trader, run = _later_run(backend, reader, "trader", None, OPEN_FIELD, values=False)
    assert run_withheld(trader, run) == {"*"}
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert (seen.score, seen.rank, seen.reasons) == (None, None, "")
    assert seen.decision == "QUALIFIED"
    # a record of open fields says what it read: nothing to withhold
    trader, run = _later_run(backend, reader, "trader", {OPEN_FIELD: "open"}, OPEN_FIELD,
                             values=False)  # fmt: skip
    assert run_withheld(trader, run) == frozenset()


def test_a_field_made_personal_since_the_run_recorded_it_open_is_withheld(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """Fix for: a frozen ``open`` record kept serving a field the site later reclassified; the
    stricter of the record and the site catalogue's current licence wins."""
    trader, run = _later_run(backend, reader, "trader", {PERSONAL_FIELD: "open"}, PERSONAL_FIELD)
    assert run_withheld(trader, run) == {PERSONAL_FIELD}


def test_a_run_before_the_record_is_read_through_the_site_catalogue(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """No backfill: a run stored before ``field_licences`` (the nightly site run, evaluated under
    every licence) shows the viewer its site fields by their current licence and withholds a
    name the site does not resolve."""
    every = {"licences": ["open", "personal"]}
    trader, run = _later_run(backend, reader, "trader", None, OPEN_FIELD, audit=every)
    assert run_withheld(trader, run) == frozenset()  # open now: visible
    trader, run = _later_run(backend, reader, "trader", None, PERSONAL_FIELD, audit=every)
    assert run_withheld(trader, run) == {PERSONAL_FIELD}
    trader, run = _later_run(backend, reader, "trader", None, OWN_FIELD, audit=every)
    assert run_withheld(trader, run) == {OWN_FIELD}


def test_a_run_evaluated_under_licences_the_viewer_also_holds_is_fully_visible(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """A trader's own run (held ``open`` only) read nothing under another licence at run time,
    whatever it records or not: another holder of ``open`` sees all of it."""
    trader, run = _later_run(
        backend, reader, "trader", None, OWN_FIELD, audit={"licences": ["open"]}
    )
    assert run_withheld(trader, run) == frozenset()
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert (seen.criteria[0].value, seen.score, seen.rank) == (7.0, 50.0, 1)


@pytest.mark.parametrize("user", ["trader", "admin"])  # a role grants no licence
def test_the_audits_narrow_misses_of_a_withheld_field_are_dropped(
    backend: MemoryBackend, reader: StoreReader, user: str
) -> None:
    """Fix for: ``ScreenerRun.audit`` served ``summary.narrow_misses`` (value, threshold, distance
    per field) to every viewer, an admin without the licence included."""
    misses = [{"field": PERSONAL_FIELD, "value": 0.29, "threshold": 0.3, "distance": 0.01},
              {"field": OPEN_FIELD, "value": 4.9, "threshold": 5.0, "distance": 0.1}]  # fmt: skip
    audit = {"summary": {"rows": 1, "passed": 1, "narrow_misses": misses}, "other": 1}
    viewer, run = _later_run(
        backend, reader, user, {PERSONAL_FIELD: "personal", OPEN_FIELD: "open"}, OPEN_FIELD,
        audit=audit,
    )  # fmt: skip
    shown = run_audit(viewer, run)
    assert shown["summary"]["narrow_misses"] == [misses[1]] and shown["other"] == 1
    assert shown["summary"]["rows"] == 1
    holder, run = _later_run(backend, reader, "me", {PERSONAL_FIELD: "personal"}, OPEN_FIELD,
                             audit=audit)  # fmt: skip
    assert run_audit(holder, run)["summary"]["narrow_misses"] == misses


def test_an_open_only_run_withholds_a_field_the_site_made_personal_since(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """The run held only ``open``, so what it read counts as open to a viewer who holds it, but
    the stricter of that and the site's current licence still wins (ADR 0069)."""
    only_open = {"licences": ["open"]}
    trader, run = _later_run(backend, reader, "trader", None, PERSONAL_FIELD, audit=only_open)
    assert run_withheld(trader, run) == {PERSONAL_FIELD}
    seen = load_results(trader, {"r3": ["EQ:AAA"]}, [run])[("r3", "EQ:AAA")]
    assert seen.criteria[0].value is None and seen.score is None and seen.rank is None


def _old_withheld(ctx: ReadContext, run: ScreenerRun) -> frozenset[str]:
    """``run_withheld`` as it was before the record skipped the values file: the stored fields
    are always read from the file and joined with the recorded ones."""
    at_run = run.audit.get("licences")
    within = isinstance(at_run, list | tuple) and set(at_run) <= set(ctx.licences)
    recorded = run.audit.get("field_licences")
    known = dict(recorded) if isinstance(recorded, dict) else {}
    stored = results._run_fields(ctx, run)
    fields = stored | frozenset(known)
    if within:
        known = {**dict.fromkeys(fields, "open"), **known}
    hidden = hidden_stored(catalogue(ctx.configs), known, fields, ctx.licences)
    if within:
        return hidden
    return hidden | {"*"} if not stored and not known and run.decisions else hidden


@pytest.mark.parametrize("user", ["trader", "me"])  # without and with every licence
@pytest.mark.parametrize(
    ("field_name", "recorded", "audit"),
    [
        (OPEN_FIELD, {OPEN_FIELD: "open"}, None),
        (PERSONAL_FIELD, {PERSONAL_FIELD: "personal"}, None),
        (PERSONAL_FIELD, {PERSONAL_FIELD: "open"}, None),  # reclassified since the run
        (OWN_FIELD, {OWN_FIELD: "personal"}, None),
        (OPEN_FIELD, {OPEN_FIELD: "open", PERSONAL_FIELD: "personal"}, None),  # a tie-break
        (PERSONAL_FIELD, {PERSONAL_FIELD: "personal"}, {"licences": ["open"]}),  # within
        (PERSONAL_FIELD, {PERSONAL_FIELD: "personal"}, {"licences": ["open", "personal"]}),
    ],
)
def test_a_recorded_run_hides_what_the_values_file_path_hid_without_reading_the_file(
    backend: MemoryBackend,
    reader: StoreReader,
    monkeypatch: pytest.MonkeyPatch,
    user: str,
    field_name: str,
    recorded: dict[str, str],
    audit: dict[str, Any] | None,
) -> None:
    """Equivalence on fixtures: a run that recorded its fields gives the same withheld set as
    reading its values file (licensed and unlicensed viewer), and shows nothing the old path
    hid, with no values read (4.3 s of an Ideas read for a viewer without ``personal``)."""
    viewer, run = _later_run(backend, reader, user, recorded, field_name, audit=audit)
    expected = _old_withheld(viewer, run)  # reads the file: the reference
    reads: list[str] = []
    real = results.run_rows_of

    def counting(*args: Any, **kwargs: Any) -> Any:
        reads.append(args[1])
        return real(*args, **kwargs)

    monkeypatch.setattr(results, "run_rows_of", counting)
    fresh = context(reader, None, user=user)  # no cached fields from the reference
    assert run_withheld(fresh, run) == expected
    assert "results/rule_screen_values" not in reads
    if user == "me":
        assert expected == frozenset()  # the holder of every licence hides nothing


def test_a_run_without_a_record_still_reads_its_values_file(
    backend: MemoryBackend, reader: StoreReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No record (a run before ``field_licences``, or an empty one): the file is read and the
    stored personal field is withheld, as before."""
    for recorded in (None, {}):
        trader, run = _later_run(backend, reader, "trader", recorded, PERSONAL_FIELD)
        reads: list[str] = []
        real = results.run_rows_of

        def counting(*args: Any, _real: Any = real, _reads: list[str] = reads, **kw: Any) -> Any:
            _reads.append(args[1])
            return _real(*args, **kw)

        monkeypatch.setattr(results, "run_rows_of", counting)
        assert run_withheld(trader, run) == {PERSONAL_FIELD}
        assert reads == ["results/rule_screen_values"]
        monkeypatch.undo()


# --- counts toward (the harness's rule, decided on the server) ---


def _edge(
    edge_id: str,
    screener: str,
    top_k: int | None,
    schedule: str = "every_session",
    side: str | None = None,
) -> Docs:
    doc: dict[str, Any] = {
        "id": edge_id, "name": edge_id.title(), "thesis": "Names keep rising.", "mechanism": "m",
        "persistence": "p", "schedule": schedule, "universe": "all_active",
        "screeners": [screener], "baselines": [], "status": "candidate",
        "sources": [{"title": "A paper"}],
        "outcome": {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
                    "start_offset_sessions": 1},
        "quality_bar": {k: f"answer {k}" for k in QUALITY_BAR},
    }  # fmt: skip
    doc["top_k"] = "all" if top_k is None else top_k
    if side is not None:
        doc["outcome"]["side"] = side
        doc["outcome"]["borrow_bps_annual"] = 30
    return {("site", "edges", edge_id): doc}


def _store(
    backend: MemoryBackend, status: str, picks: Sequence[str] = (), edge_id: str = "drift",
    screener: str = "beta", day: Any = D1,
) -> None:  # fmt: skip
    """The nightly's row for (``edge_id``, ``screener``) at ``day`` (ADR 0081)."""
    row = EdgePicks(edge_id, screener, status, tuple(f"EQ:{p}" for p in picks), top_k=2)
    frame = edge_picks_frame([row], day, f"picks-{edge_id}-{screener}", T)
    ResultWriter(backend).write_result(RESULT, day, f"picks-{edge_id}-{screener}", frame)


def _toward(ctx: ReadContext, owner: str, screener: str) -> dict[str, tuple[PickEdge, ...]]:
    run = latest_run(ctx, owner, screener).run
    assert run is not None
    page = load_result_page(ctx, run)
    return {r.instrument_id: r.counts_toward for r in page.results}


def _codes(found: dict[str, tuple[PickEdge, ...]]) -> dict[str, list[tuple[str, int | None]]]:
    return {i: [(e.code, e.place) for e in edges] for i, edges in found.items()}


def test_a_pick_counts_where_the_edges_own_stored_picks_put_it(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    """The edge's stored list is the truth, whatever the run's own rank was."""
    _store(backend, PICKED, ["CCC"])
    found = _toward(context(reader, _edge("drift", "beta", top_k=2)), "site", "beta")
    assert _codes(found) == {"EQ:CCC": [(COUNTS, 1)]}
    (ccc,) = found["EQ:CCC"]
    assert (ccc.edge_id, ccc.edge_name, ccc.counts, ccc.top_k) == ("drift", "Drift", True, 2)


def test_a_session_with_no_stored_picks_says_not_stored_never_an_older_night(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    _store(backend, PICKED, ["CCC"], day=D0)  # an older session's picks are not this one's
    found = _toward(context(reader, _edge("drift", "beta", top_k=2)), "site", "beta")
    assert {e.code for edges in found.values() for e in edges} == {NOT_STORED}
    assert not any(e.counts for edges in found.values() for e in edges)


def test_an_edge_with_no_row_is_not_stored_while_another_has_its_picks(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    _store(backend, PICKED, ["CCC"], edge_id="alpha")
    ctx = context(reader, {**_edge("alpha", "beta", 2), **_edge("zeta", "beta", 2)})
    found = _toward(ctx, "site", "beta")
    assert [(e.edge_id, e.code) for e in found["EQ:CCC"]] == [
        ("alpha", COUNTS),
        ("zeta", NOT_STORED),
    ]


def test_a_pick_the_regime_gate_held_back_is_never_counted(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)  # AAA QUALIFIED, BBB and DDD PAUSED, CCC REJECT
    _store(backend, PICKED, ["AAA"], screener="alpha")
    found = _toward(context(reader, _edge("drift", "alpha", top_k=None)), "site", "alpha")
    assert _codes(found) == {
        "EQ:AAA": [(COUNTS, 1)],
        "EQ:BBB": [(PAUSED, None)],
        "EQ:CCC": [(NOT_COUNTED, None)],
        "EQ:DDD": [(PAUSED, None)],
    }


def test_a_screener_no_edge_lists_has_none(reader: StoreReader) -> None:
    assert _toward(context(reader), "site", "beta")["EQ:CCC"] == ()


def test_a_session_the_schedule_does_not_decide_and_an_unjudged_edge_count_nothing(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    _store(backend, NOT_DECISION_DAY, edge_id="monthly")
    _store(backend, "unjudged", edge_id="shorty")
    _store(backend, SKIPPED, edge_id="gap")
    ctx = context(
        reader,
        {
            **_edge("monthly", "beta", 5, schedule="month_end"),
            **_edge("shorty", "beta", 5, side="short"),
            **_edge("gap", "beta", 5),
        },
    )
    for edges in _toward(ctx, "site", "beta").values():
        assert [(e.edge_id, e.code, e.counts, e.place) for e in edges] == [
            ("gap", NOT_STORED, False, None),
            ("monthly", NOT_A_DECISION_DAY, False, None),
            ("shorty", UNJUDGED, False, None),
        ]


def test_a_users_own_edge_is_not_stored_whatever_a_row_says(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    _store(backend, PICKED, ["BBB"], edge_id="mine")
    own = {("me", "edges", "mine"): _edge("mine", "beta", 2)[("site", "edges", "mine")]}
    found = _toward(context(reader, own), "site", "beta")
    assert [(e.edge_id, e.code) for e in found["EQ:CCC"]] == [("mine", NOT_STORED)]


def test_a_viewers_own_run_is_not_judged_by_the_sites_picks(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    _store(backend, PICKED, ["BBB"])
    found = _toward(context(reader, _edge("drift", "beta", top_k=2)), "me", "beta")  # me's beta
    assert {e.code for edges in found.values() for e in edges} == {NOT_STORED}


# ---------------------------------------------------------------------- filters (ADR 0082)
def _big(docs: Docs | None = None, user: str = "full", store: MemoryBackend | None = None) -> Any:
    """The twelve-pick run ``big`` (dollar volume on S000..S007, IV on all) as ``user`` reads it."""
    reader = StoreReader(store or filter_store())
    ctx = context(reader, {**FILTER_DOCS, **(docs or {})}, user=user)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    return ctx, run


FILTER_DOCS: Docs = {
    **DOCS,
    ("site", "filters", "screener_results"): {
        **RESULTS_FILTERS,
        "filter": [*RESULTS_FILTERS["filter"], IV_FILTER],
    },
}
BIG = 13  # twelve picks and a reject


def _ids(page: ResultPage) -> list[str]:
    return [r.instrument_id for r in page.results]


def test_filters_narrow_the_whole_run_before_it_is_paged() -> None:
    ctx, run = _big()
    only = [FilterInput("dollar_volume", min=50_000_000)]
    pages = [load_result_page(ctx, run, None, (), n, 2, only) for n in (1, 2, 3)]
    assert [_ids(p) for p in pages] == [["EQ:S004", "EQ:S005"], ["EQ:S006", "EQ:S007"], []]
    assert {p.total for p in pages} == {4}  # S004..S007 sit past the first page
    assert all(
        p.facets is not None and (p.facets.total, p.facets.matched) == (BIG, 4) for p in pages
    )
    plain = load_result_page(ctx, run, None, (), 1, 100)
    assert plain.total == BIG and plain.facets is not None and plain.facets.matched == BIG


def test_the_old_arguments_equal_the_filters_they_map_onto() -> None:
    ctx, run = _big()
    old = load_result_page(ctx, run, ResultQuery(decisions=("qualified",), change="new"))
    new = load_result_page(
        ctx, run, None, (), 1, 100,
        [FilterInput("decision", ["QUALIFIED"]), FilterInput("change", ["new"])],
    )  # fmt: skip
    assert old.total == new.total == len(old.results) > 0
    assert old == new
    assert load_result_page(ctx, run, ResultQuery(decisions=("reject",))).total == 1
    with pytest.raises(FilterRefusedError, match="twice"):  # set both ways
        load_result_page(ctx, run, ResultQuery(change="new"), (), 1, 5, [FilterInput("change")])


def test_unknown_never_passes_a_filter_and_is_counted() -> None:
    ctx, run = _big()
    zero = load_result_page(ctx, run, None, (), 1, 100, [FilterInput("dollar_volume", min=0)])
    assert zero.total == 8  # a min of 0 admits no null
    assert zero.facets is not None
    [volume] = [f for f in zero.facets.items if f.id == "dollar_volume"]
    assert (volume.unknown, volume.removes) == (BIG - 8, BIG - 8)
    window = [FilterInput("earnings", within=Within(100, WindowUnit.SESSIONS))]
    assert load_result_page(ctx, run, None, (), 1, 100, window).total == 6


def test_pages_of_a_filtered_run_partition_it_with_q_applied_after() -> None:
    ctx, run = _big()
    only = [FilterInput("dollar_volume", min=30_000_000)]
    seen = [i for n in (1, 2, 3) for i in _ids(load_result_page(ctx, run, None, (), n, 3, only))]
    assert seen == [f"EQ:S{n:03d}" for n in range(2, 8)]
    searched = load_result_page(ctx, run, ResultQuery(q="S00"), (), 1, 100, only)
    assert searched.total == 6 and searched.facets is not None
    assert searched.facets.total == BIG  # the counts are of the run, not of the search
    assert [
        r.instrument_id
        for r in load_result_page(ctx, run, ResultQuery(q="S003"), (), 1, 9, only).results
    ] == ["EQ:S003"]


def test_a_filter_the_viewer_is_not_offered_is_refused() -> None:
    ctx, run = _big(user="bare")
    with pytest.raises(FilterRefusedError):
        load_result_page(ctx, run, None, (), 1, 5, [FilterInput("iv", min=0.3)])
    assert "iv" not in {f.id for f in load_served_filters(ctx, "screener_results").filters}


def test_changing_a_hidden_licence_fields_values_changes_no_count() -> None:
    """The leak test: two stores differing only in the stored ``iv30_ibkr``; the viewer without
    the personal licence reads the same page, total and every facet from both."""
    low, high = filter_store(lambda n: 0.05), filter_store(lambda n: 0.95)
    given = [FilterInput("dollar_volume", min=20_000_000), FilterInput("decision", ["QUALIFIED"])]
    shapes = []
    for store in (low, high):
        ctx, run = _big(user="bare", store=store)
        shapes.append(load_result_page(ctx, run, None, (), 1, 100, given))
    assert shapes[0] == shapes[1]
    assert shapes[0].facets is not None and all(f.id != "iv" for f in shapes[0].facets.items)
    seen = []
    for store in (low, high):
        ctx, run = _big(store=store)
        seen.append(
            load_result_page(ctx, run, None, (), 1, 100, [FilterInput("iv", min=0.5)]).total
        )
    assert seen[0] != seen[1]  # the holder of the licence reads the values


def test_a_withheld_rank_is_unknown_to_a_filter(ctx: ReadContext, reader: StoreReader) -> None:
    trader = context(reader, user="trader")  # the run read personal fields: rank is withheld
    run = latest_run(trader, "site", "alpha").run
    assert run is not None and run_withheld(trader, run)
    page = load_result_page(trader, run, None, (), 1, 100, [FilterInput("rank", min=1)])
    assert page.total == 0 and page.facets is not None
    [rank] = [f for f in page.facets.items if f.id == "rank"]
    assert rank.unknown == page.facets.total == 3


def test_a_gap_is_disclosed_only_for_the_tables_of_a_set_filter(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The small store has no volume or earnings tables: they are read for the facets, and
    named in ``missing`` only when a filter on them is set; a decision filter names none."""
    assert _page(ctx, ResultQuery(decisions=("qualified",))).missing == ()
    assert _page(ctx).missing == ()
    page = load_result_page(
        ctx, latest_run(ctx, "site", "alpha").run, None, (), 1, 5,  # type: ignore[arg-type]
        [FilterInput("dollar_volume", min=1)],
    )  # fmt: skip
    assert page.missing == ("rollups/instrument/volume@v1",)


def test_a_new_search_or_sort_reads_the_filter_pass_once(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[int] = []
    real = results._filter_run
    monkeypatch.setattr(results, "_filter_run", lambda *a: ran.append(1) or real(*a))
    for query in (ResultQuery(), ResultQuery(q="a"), ResultQuery(sort="-score")):
        _page(ctx, query)
    assert ran == [1]


# ---------------------------------------------------- rank_change and gate counts (ADR 0082)
D2 = D1 + timedelta(days=1)


def _stage(
    backend: MemoryBackend,
    day: Any,
    run_id: str,
    owner: str,
    config_id: str,
    rows: list[tuple[str, str, int]],
    version: int = 1,
    gates: tuple[str, str] = ("", ""),
) -> None:
    """A run of ``rows`` (symbol, decision, rank); ``gates``: the stored (failed, near_missed)."""
    frame = [
        {"instrument_id": f"EQ:{s}", "user_id": owner, "config_id": config_id,
         "config_version": version, "config_hash": "h", "decision": d, "score": 1.0,
         "rank": n, "tie_break": None, "flags": "", "reasons": "", "failed": gates[0],
         "near_missed": gates[1], "missing": ""}
        for s, d, n in rows
    ]  # fmt: skip
    when = T + timedelta(days=(day - D1).days, hours=5)
    bar = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), "open": 1.0, "high": 1.0,
           "low": 1.0, "close": 1.0, "volume": 1.0}  # fmt: skip
    if day == D2:  # a session needs its bars to be read
        StoreWriter(backend).write_table("bars/1d", day, f"bars-{day}", stamped([bar], day, "b"))
    StoreWriter(backend).write_result("rule_screen", day, run_id, stamped(frame, day, run_id, when))


def _moved(ctx: ReadContext, owner: str = "site", config_id: str = "alpha") -> dict[str, Any]:
    run = latest_run(ctx, owner, config_id).run
    assert run is not None
    page = load_result_page(ctx, run, None, (), 1, 100)
    return {r.instrument_id: r.rank_change for r in page.results}


def test_rank_change_is_the_previous_rank_minus_the_rank(ctx: ReadContext) -> None:
    # r-1 (D0): BBB 1, CCC 2, AAA 3; r1 (D1): AAA 1, BBB 2, CCC 3
    assert _moved(ctx) == {"EQ:AAA": 2, "EQ:BBB": -1, "EQ:CCC": -1}
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    up = load_result_page(ctx, run, None, (), 1, 100, [FilterInput("rank_moved_up", min=1)])
    assert _ids(up) == ["EQ:AAA"] and up.total == 1


def test_rank_change_is_unknown_never_zero(backend: MemoryBackend, reader: StoreReader) -> None:
    # no previous run: me's beta ran only in D1
    assert _moved(context(reader), "me", "beta") == {
        "EQ:BBB": None, "EQ:DDD": None, "EQ:AAA": None,
    }  # fmt: skip
    # the ticker is missing from the previous run: DDD joins alpha's later D1 run
    _stage(backend, D1, "r9", "site", "alpha", [("AAA", "QUALIFIED", 1), ("DDD", "QUALIFIED", 2)])
    found = _moved(context(StoreReader(backend)))
    assert found == {"EQ:AAA": 2, "EQ:DDD": None}
    # a viewer who may not see the order has no change, and the filter keeps no row
    trader = context(reader, user="trader")
    assert set(_moved(trader).values()) == {None}
    run = latest_run(trader, "site", "alpha").run
    assert run is not None
    page = load_result_page(trader, run, None, (), 1, 100, [FilterInput("rank_moved_up", min=1)])
    assert page.total == 0 and page.facets is not None


def test_rank_change_is_unknown_when_the_previous_run_is_withheld(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    # the viewer reads today's run in full (no personal field) but D0's r-1 stored none, so it
    # is withheld whole for a viewer without every licence: the places moved are not comparable
    _stage(backend, D1, "r9", "site", "alpha", [("AAA", "QUALIFIED", 1), ("BBB", "WATCH", 2)])
    ctx = context(StoreReader(backend), user="trader")
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    previous = runs.load_previous_run(ctx, run)
    assert previous is not None and run_withheld(at_session(ctx, previous.session), previous)
    assert set(_moved(ctx).values()) == {None}


def test_rank_change_is_unknown_across_a_config_version_change(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    _stage(backend, D1, "g1", "me", "gamma", [("CCC", "QUALIFIED", 1), ("AAA", "QUALIFIED", 2)], 2)
    assert _moved(context(StoreReader(backend)), "me", "gamma") == {"EQ:CCC": None, "EQ:AAA": None}
    _stage(backend, D1, "g2", "me", "gamma", [("CCC", "QUALIFIED", 1)], 1)  # same version
    assert _moved(context(StoreReader(backend)), "me", "gamma") == {"EQ:CCC": 0}


def test_the_previous_run_is_the_one_before_the_session_not_the_latest(
    backend: MemoryBackend,
) -> None:
    before = _moved(context(StoreReader(backend)))
    _stage(backend, D2, "r5", "site", "alpha", [("CCC", "QUALIFIED", 1), ("AAA", "QUALIFIED", 2)])
    after = StoreReader(backend)
    # D1's value is unchanged by the later run; D2 is compared with D1's run
    assert _moved(at_session(context(after), D1)) == before
    assert _moved(context(after)) == {"EQ:CCC": 2, "EQ:AAA": -1}


def test_gate_counts_are_stored_counts_and_unknown_when_withheld(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    # r1 stored no failed / near-missed gates: 0, which is not unknown, for a viewer who sees it
    run = latest_run(context(reader), "site", "alpha").run
    assert run is not None
    page = load_result_page(context(reader), run, None, (), 1, 100)
    assert {(r.near_misses, r.gates_failing) for r in page.results} == {(0, 0)}
    # a viewer who may not see the run's values gets no count: which gates a row missed leaks them
    trader = context(reader, user="trader")
    hidden = load_result_page(trader, run, None, (), 1, 100)
    assert {(r.near_misses, r.gates_failing) for r in hidden.results} == {(None, None)}
    assert load_result_page(
        trader, run, None, (), 1, 100, [FilterInput("near_misses", min=0)]
    ).total == 0  # fmt: skip
    # a run that stored lists: near-missed ones count in both, failed ones only in gates_failing
    _stage(backend, D2, "r6", "me", "gamma", [("AAA", "WATCH", 1)], gates=("a,b", "c"))
    ctx = context(StoreReader(backend))
    own = latest_run(ctx, "me", "gamma").run
    assert own is not None
    seen = load_result_page(ctx, own, None, (), 1, 100, [FilterInput("gates_failing", min=3)])
    assert [(r.near_misses, r.gates_failing) for r in seen.results] == [(1, 3)]
