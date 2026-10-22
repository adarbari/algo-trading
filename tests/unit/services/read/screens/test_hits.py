from datetime import date

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context, weigh
from algotrade.services.read.screens import results, runs
from algotrade.services.read.screens.hits import ScreenerHit, load_screener_hits
from algotrade.services.read.screens.results import load_results, load_run_changes
from algotrade.services.read.screens.runs import (
    RULE_SCREEN,
    RUN_COLUMNS,
    SCREEN_PICKS,
    is_picked,
    load_latest_runs,
    run_rows,
)
from algotrade.services.read.screens.screeners import load_screeners
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.screens.conftest import (
    D0,
    D1,
    T,
    context,
    screens_store,
    write_gated,
    write_picks,
)


def _hits(found: dict[str, tuple], iid: str) -> list[tuple[str, str]]:  # type: ignore[type-arg]
    return [(h.screener.id, h.result.decision) for h in found[iid]]


def test_the_screeners_that_picked_each_instrument_in_the_session(ctx: ReadContext) -> None:
    found = load_screener_hits(ctx, ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:DDD", "EQ:AAA"])
    assert list(found) == ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:DDD"]
    assert _hits(found, "EQ:AAA") == [("alpha", "QUALIFIED")]  # beta SKIPPED it: no hit
    assert _hits(found, "EQ:BBB") == [("alpha", "WATCH"), ("beta", "QUALIFIED")]
    assert _hits(found, "EQ:CCC") == []  # alpha rejected it; gamma ran only on D0
    assert _hits(found, "EQ:DDD") == [("beta", "QUALIFIED")]
    hit = found["EQ:BBB"][1]
    assert (hit.screener.owner, hit.result.run_id, hit.result.score) == ("me", "rb", 90.0)
    assert found["EQ:AAA"][0].result.change == "new"  # alpha rejected it on D0


def test_an_earlier_session_has_its_own_hits(reader: StoreReader) -> None:
    base = context(reader)
    earlier = open_context(reader, base.configs, UserContext("me"), D0)
    found = load_screener_hits(earlier, ["EQ:CCC", "EQ:AAA"])
    assert _hits(found, "EQ:CCC") == [("alpha", "QUALIFIED"), ("gamma", "QUALIFIED")]
    assert _hits(found, "EQ:AAA") == []
    assert load_screener_hits(earlier, []) == {}


def test_an_instrument_asked_again_reads_nothing_and_a_new_one_reads_only_its_own_values(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every ticker opened in Explore used to be served from an index of every pick's stored
    values (331 MB on the real store): an instrument's results are read for it alone, once."""
    asked: list[list[str]] = []
    real = results._read_values

    def counting(ctx_: ReadContext, runs: object, ids: list[str] | None, wanted: object) -> object:
        asked.append(sorted(ids or []))
        return real(ctx_, runs, ids, wanted)  # type: ignore[arg-type]

    monkeypatch.setattr(results, "_read_values", counting)
    load_screener_hits(ctx, ["EQ:AAA"])
    assert asked == [["EQ:AAA"]]
    load_screener_hits(ctx, ["EQ:AAA"])  # kept
    assert asked == [["EQ:AAA"]]
    load_screener_hits(ctx, ["EQ:DDD", "EQ:CCC"])  # CCC was picked by nobody: not read
    assert asked == [["EQ:AAA"], ["EQ:DDD"]]


# ---- the whole-session index this replaced, kept as the oracle ----------------------------------


def _old_session_hits(ctx: ReadContext) -> dict[str, tuple[ScreenerHit, ...]]:
    """Every pick of the user's screeners with its full result, built at once (what
    ``_session_hits`` / ``_build`` did before the index held only who picked what)."""
    screeners = load_screeners(ctx)
    latest = load_latest_runs(ctx, [(s.owner, s.id) for s in screeners])
    runs = [(s, r) for s in screeners if (r := latest[(s.owner, s.id)].run) is not None]
    changes = {run.run_id: load_run_changes(ctx, run) for _, run in runs}
    picked = {
        run.run_id: [
            str(i)
            for i, d in zip(run_rows(ctx, run)["instrument_id"], run_rows(ctx, run)["decision"],
                            strict=True)
            if is_picked(str(d))
        ]
        for _, run in runs
    }  # fmt: skip
    found = load_results(ctx, picked, [run for _, run in runs], changes)
    out: dict[str, list[ScreenerHit]] = {}
    for screener, run in runs:
        for iid in picked[run.run_id]:
            result = found.get((run.run_id, iid))
            if result is not None and is_picked(result.decision):
                out.setdefault(iid, []).append(ScreenerHit(screener, result))
    return {i: tuple(hits) for i, hits in out.items()}


@pytest.mark.parametrize("viewer", ["me", "trader"])  # a personal-data licence, and none
def test_the_hits_of_every_instrument_are_what_the_whole_session_index_gave(
    reader: StoreReader, viewer: str
) -> None:
    ids = ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:DDD", "EQ:ZZZ"]
    oracle = _old_session_hits(context(reader, user=viewer))
    one_by_one = context(reader, user=viewer)
    together = context(reader, user=viewer)
    found = load_screener_hits(together, ids)
    for iid in ids:
        want = oracle.get(iid, ())
        assert found[iid] == want
        assert load_screener_hits(one_by_one, [iid])[iid] == want
    assert any(oracle.values())  # the store has hits to compare


def test_the_index_weighs_who_picked_what_not_their_results(reader: StoreReader) -> None:
    ctx = context(reader)
    load_screener_hits(ctx, [])
    index = [w for k, w in ctx.cache._weights.items() if k[-1] == "index"]
    assert len(index) == 1 and 0 < index[0] < 5_000
    assert weigh(_old_session_hits(ctx)) > 10 * index[0]  # the old entry held every result


# ---- the pick index from the runs' stored picks (results/screen_picks) --------------------------

IDS = ["EQ:AAA", "EQ:BBB", "EQ:CCC", "EQ:DDD", "EQ:ZZZ"]


def _frame(backend: MemoryBackend, framed: tuple[tuple[date, str], ...]) -> None:
    """Write the ``screen_picks`` file of each ``(day, run id)`` from its stored rule rows."""
    reader = StoreReader(backend)
    for day, run_id in framed:
        at = open_context(reader, context(reader).configs, UserContext("me"), day)
        rows = runs.run_rows_of(at, RULE_SCREEN, run_id)
        write_picks(backend, day, run_id, rows.to_dict("records"), T)


def _store(framed: tuple[tuple[date, str], ...], gated: bool = False) -> MemoryBackend:
    backend = screens_store()
    if gated:
        write_gated(backend)  # r2 supersedes r1; BBB and DDD PAUSED
    _frame(backend, framed)
    return backend


# r0 is superseded by r1 (its DDD pick must never show); rs and rg stay unframed: they fall back
FRAMED = ((D1, "r0"), (D1, "r1"), (D1, "rb"), (D0, "r-1"))


@pytest.mark.parametrize("gated", [False, True])
@pytest.mark.parametrize("session", [D1, D0])  # D0: every run there is a first run, no change
def test_hits_from_the_stored_picks_equal_the_hits_from_the_rows(
    gated: bool, session: date
) -> None:
    """Equivalence (owner brief): one store with framed, superseded, PAUSED, first and unframed
    runs; the hits of every instrument equal those of the oracle built from every row."""
    framed = (*FRAMED, (D1, "r2")) if gated else FRAMED
    backend = _store(framed, gated)
    reader = StoreReader(backend)
    configs = context(reader).configs
    at = lambda: open_context(reader, configs, UserContext("me"), session)  # noqa: E731
    oracle = _old_session_hits(at())
    found = load_screener_hits(at(), IDS)
    for iid in IDS:
        assert found[iid] == oracle.get(iid, ())
    assert any(oracle.values())


def test_a_run_with_no_picks_file_falls_back_to_its_rows_never_to_no_picks() -> None:
    backend = _store(())  # no run framed: every run is read from its rule_screen rows
    ctx = context(StoreReader(backend))
    found = load_screener_hits(ctx, IDS)
    assert _hits(found, "EQ:BBB") == [("alpha", "WATCH"), ("beta", "QUALIFIED")]
    assert _hits(found, "EQ:DDD") == [("beta", "QUALIFIED")]


def test_run_picks_are_read_once_per_run_not_per_pick_or_per_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from algotrade.services.read.screens.ideas import load_ideas  # noqa: PLC0415

    reads: list[tuple[str, str, bool]] = []
    real = runs.run_rows_of

    def counting(ctx_: ReadContext, table: str, run_id: str, columns=None, instruments=None):  # type: ignore[no-untyped-def]
        reads.append((table, run_id, columns == RUN_COLUMNS))
        return real(ctx_, table, run_id, columns, instruments)

    monkeypatch.setattr(runs, "run_rows_of", counting)
    monkeypatch.setattr(results, "run_rows_of", counting)
    ctx = context(StoreReader(_store(FRAMED)))
    load_screener_hits(ctx, IDS)
    for iid in IDS:  # one by one: still no new read of the picks
        load_screener_hits(ctx, [iid])
    load_ideas(ctx, 50)
    picks = [run_id for table, run_id, _ in reads if table == SCREEN_PICKS]
    # each run's picks once: alpha's r1 (not the superseded r0), beta's rb, and alpha's previous
    # run r-1 (the change of a hit); rs is a site beta the user's own beta shadows
    assert sorted(picks) == ["r-1", "r1", "rb"]
    assert not [r for r in reads if r[2] and r[0] == RULE_SCREEN and r[1] in {"r1", "rb", "r-1"}], (
        "a framed run's every row is never read for its picks"
    )


# ---- the reads of one request: each file once, the heaviest one column-pruned --------------------


def _counted_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, str, tuple[str, ...], tuple[str, ...]]]:
    """Every ``run_rows_of`` read of the run files: (table, run id, columns, instruments)."""
    reads: list[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = []
    real = results.run_rows_of

    def counting(ctx_: ReadContext, table: str, run_id: str, columns=None, instruments=None):  # type: ignore[no-untyped-def]
        reads.append((table, run_id, tuple(columns or ()), tuple(instruments or ())))
        return real(ctx_, table, run_id, columns, instruments)

    for module in (runs, results):
        monkeypatch.setattr(module, "run_rows_of", counting)
    return reads


def test_a_viewer_without_every_licence_reads_the_fields_of_a_run_from_four_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fields a run read were taken from the run's whole values file with all ten columns
    (the heaviest read of an Ideas or hits request on a fresh process); four are used."""
    reads = _counted_reads(monkeypatch)
    ctx = context(StoreReader(_store(FRAMED)), user="trader")  # holds no personal-data licence
    load_screener_hits(ctx, IDS)
    whole = [r for r in reads if r[0] == "results/rule_screen_values" and not r[3]]
    assert whole, "the fields of a run are read from its whole values file"
    assert all(r[2] == results.FIELD_COLUMNS for r in whole)


@pytest.mark.parametrize("viewer", ["me", "trader"])
def test_a_request_reads_each_run_file_once_per_table_and_instrument_set(
    monkeypatch: pytest.MonkeyPatch, viewer: str
) -> None:
    """Read-count test: hits and Ideas read a run's values and rows once for the instruments
    asked (an id listed twice, as a top pick that is also on the page, is read once), and a run's
    picks once however many instruments, hits or screeners ask."""
    from algotrade.services.read.screens.ideas import load_ideas  # noqa: PLC0415

    reads = _counted_reads(monkeypatch)
    reader = StoreReader(_store(FRAMED))
    load_screener_hits(context(reader, user=viewer), IDS)  # one request each, nothing shared
    del reads[:]
    load_ideas(context(reader, user=viewer), 50)
    asked = [r for r in reads if r[3]]
    assert all(len(set(r[3])) == len(r[3]) for r in asked), "an instrument asked twice in one read"
    # Ideas asks a run for the union of its tops and the page in one read, never one per pick
    values = [(r[1], r[3]) for r in asked if r[0] == "results/rule_screen_values"]
    assert len(values) == len(set(values))
    picks = [run_id for table, run_id, _, _ in reads if table == SCREEN_PICKS]
    assert len(picks) == len(set(picks))  # Ideas reads each run's picks once for its whole ranking
