from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, at_session, open_context
from algotrade.services.read.screens import results, runs
from algotrade.services.read.screens.results import ResultQuery
from algotrade.services.read.screens.runs import (
    RULE_SCREEN,
    DecisionCount,
    last_run_rows,
    latest_run,
    load_latest_runs,
    load_previous_run,
    picked_mask,
    run_rows,
)
from algotrade.services.read.values import UnknownCode
from algotrade.services.screening.rule_results import NOT_PICKED, change_counts, is_picked
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference
from tests.unit.services.read.screens.conftest import (
    D0,
    D1,
    T,
    context,
    screens_store,
    write_gated,
    write_run,
)


def _on(reader: StoreReader, day: date) -> ReadContext:
    return open_context(reader, MemoryConfigStore({}), UserContext("me"), day)


def test_the_latest_run_of_the_session_wins(ctx: ReadContext) -> None:
    found = latest_run(ctx, "site", "alpha")
    run = found.run
    assert found.not_run is None and run is not None
    assert (run.run_id, run.owner, run.session, run.status) == ("r1", "site", D1, "complete")
    assert run.knowledge_ts == T + timedelta(hours=1)
    assert run.config_version == 1
    assert run.decisions == (
        DecisionCount("QUALIFIED", 1), DecisionCount("REJECT", 1), DecisionCount("WATCH", 1)
    )  # fmt: skip
    assert run.picked == 2  # QUALIFIED, WATCH
    assert list(run_rows(ctx, run)["instrument_id"]) == ["EQ:AAA", "EQ:BBB", "EQ:CCC"]


def test_no_run_for_the_session_is_not_run_never_an_older_one(ctx: ReadContext) -> None:
    found = latest_run(ctx, "me", "gamma")  # gamma ran on D0 only
    assert found.run is None
    assert found.not_run is not None and found.not_run.code is UnknownCode.NOT_RUN
    assert found.not_run.cause.text == "gamma (me) has no run in results/rule_screen for 2026-10-01"


def test_a_run_without_a_record_has_no_status(ctx: ReadContext) -> None:
    runs = load_latest_runs(ctx, [("me", "beta"), ("site", "beta")])
    mine, site = runs[("me", "beta")].run, runs[("site", "beta")].run
    assert mine is not None and site is not None
    assert (mine.run_id, mine.status, mine.picked) == ("rb", None, 2)
    assert site.run_id == "rs"


def test_a_session_with_no_results_partition_is_not_run(reader: StoreReader) -> None:
    found = latest_run(_on(reader, D1 + timedelta(days=1)), "site", "alpha")
    assert found.run is None and found.not_run is not None
    assert found.not_run.code is UnknownCode.NOT_RUN
    assert found.not_run.cause.text == "results/rule_screen has no partition for 2026-10-02"


def test_an_earlier_session_reads_its_own_runs(reader: StoreReader) -> None:
    older = latest_run(_on(reader, D0), "me", "gamma")
    assert older.run is not None and older.run.session == D0


def test_picked_is_every_decision_but_reject_skipped_unknown_paused() -> None:
    assert all(is_picked(d) for d in ("QUALIFIED", "WATCH", "EVENT_RISK", "LIQUIDITY_RISK"))
    assert not any(is_picked(d) for d in ("REJECT", "SKIPPED", "UNKNOWN", "PAUSED"))


def test_paused_rows_are_counted_apart_and_never_picked(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    run = latest_run(_on(reader, D1), "site", "alpha").run
    assert run is not None and run.run_id == "r2"
    assert (run.picked, run.paused, run.regime) == (1, 2, "STRESS")  # only AAA is picked
    assert DecisionCount("PAUSED", 2) in run.decisions  # the whole run, as stored


def test_a_run_without_the_stamp_has_no_regime_and_nothing_paused(ctx: ReadContext) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None and (run.regime, run.paused) == (None, 0)


def test_a_run_carries_its_record_stats(ctx: ReadContext) -> None:
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None and set(run.audit) == {"field_licences"}  # no other stats
    beta = latest_run(ctx, "me", "beta").run
    assert beta is not None and beta.audit == {}  # no record at all
    assert (beta.coverage, beta.missing_tables) == (None, ())
    assert beta.missing_optional_tables == ()


def test_a_partial_run_names_the_tables_it_ran_without(backend: MemoryBackend) -> None:
    """The run's own coverage and ``stats["missing_tables"]``, not the session's as read now
    (2026-10-07: breakout's PARTIAL run lacked trend_stats, the page named other tables)."""
    stats = {"coverage": "PARTIAL", "missing_tables": ["rollups/instrument/vol_stats@v1",
             "rollups/instrument/trend_stats@v2"], "selection": {"missing_tables": []}}  # fmt: skip
    StoreWriter(backend).save_run(
        RunRecord("rs", "screen-beta-site", D1, T).finish(T, complete=False, stats=stats)
    )
    run = latest_run(context(StoreReader(backend), user="site"), "site", "beta").run
    assert run is not None and run.status == "partial"
    assert run.coverage == "PARTIAL"
    assert run.missing_tables == (
        "rollups/instrument/trend_stats@v2", "rollups/instrument/vol_stats@v1",
    )  # fmt: skip


def test_a_complete_run_without_an_optional_table_names_it(backend: MemoryBackend) -> None:
    """ADR 0055: ``stats["missing_optional_tables"]`` reaches the read model, so a COMPLETE run
    without ibkr_iv (IB Gateway down) does not look clean; it is not in ``missing_tables``."""
    stats = {"coverage": "COMPLETE", "missing_tables": [],
             "missing_optional_tables": ["rollups/instrument/ibkr_iv@v1"]}  # fmt: skip
    StoreWriter(backend).save_run(
        RunRecord("rs", "screen-beta-site", D1, T).finish(T, complete=True, stats=stats)
    )
    run = latest_run(context(StoreReader(backend), user="site"), "site", "beta").run
    assert run is not None and run.status == "complete"
    assert (run.missing_tables, run.missing_optional_tables) == (
        (), ("rollups/instrument/ibkr_iv@v1",)
    )  # fmt: skip


def test_the_previous_run_is_the_screeners_run_in_the_previous_session(
    ctx: ReadContext, reader: StoreReader
) -> None:
    alpha = latest_run(ctx, "site", "alpha").run
    assert alpha is not None
    previous = load_previous_run(ctx, alpha)
    assert previous is not None and (previous.run_id, previous.session) == ("r-1", D0)
    beta = latest_run(ctx, "me", "beta").run
    assert beta is not None and load_previous_run(ctx, beta) is None  # beta did not run on D0
    gamma = latest_run(_on(reader, D0), "me", "gamma").run
    assert gamma is not None and load_previous_run(_on(reader, D0), gamma) is None  # no earlier


def test_picked_mask_is_is_picked_on_every_row() -> None:
    decisions = pd.Series([*sorted(NOT_PICKED), "PICK", "WATCH", None], dtype="string")
    assert picked_mask(decisions).tolist() == [is_picked(str(d)) for d in decisions]


def test_pick_ids_read_the_run_rows_only_in_rank_order(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the calendar's ids came from load_results: the criterion value rows were the 3.4 s
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    read: list[str] = []
    real = results.run_rows_of

    def counting(c: ReadContext, table: str, *args: Any, **kwargs: Any) -> Any:
        read.append(table)
        return real(c, table, *args, **kwargs)

    monkeypatch.setattr(results, "run_rows_of", counting)
    found = runs.load_pick_ids(ctx, run, 100)
    assert read == []  # no results/rule_screen_values read
    rows = runs.run_rows(ctx, run)
    mine = [
        str(i)
        for i, d in zip(rows["instrument_id"], rows["decision"], strict=True)
        if runs.is_picked(str(d)) or d == runs.PAUSED
    ]
    assert found.instrument_ids == tuple(mine) and found.total == len(mine) > 0
    assert runs.load_pick_ids(ctx, run, 1) == runs.PickIds(tuple(mine[:1]), found.total)


@pytest.fixture(params=["memory", "local"])
def either(request: pytest.FixtureRequest, tmp_path: Path) -> Backend:
    """A session of both backends: ``alpha`` ran twice (``r0``, then ``r1`` with fewer rows),
    ``beta`` once for ``me`` and once for ``site``, and ``alpha`` has a pending run ``r9``."""
    backend: Backend = MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path)
    w = StoreWriter(backend)
    write_reference(w, D1, {s: f"EQ:{s}" for s in ("AAA", "BBB", "CCC", "DDD")})
    bar = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(D1, tz="UTC"), "open": 1.0, "high": 1.0,
           "low": 1.0, "close": 1.0, "volume": 1.0}  # fmt: skip
    w.write_table("bars/1d", D1, "bars", stamped([bar], D1, "bars"))
    first = [("AAA", "QUALIFIED", 5.0, None), ("BBB", "REJECT", 0.0, None),
             ("CCC", "WATCH", 3.0, 1.0), ("DDD", "QUALIFIED", 9.0, None)]  # fmt: skip
    write_run(w, D1, "r0", "site", "alpha", first)
    write_run(w, D1, "r1", "site", "alpha", first[:2][::-1], knowledge=T + timedelta(hours=1))
    write_run(w, D1, "rb", "me", "beta", first[2:])
    write_run(w, D1, "rs", "site", "beta", first[:1])
    for run_id in ("r1", "rb", "rs", "r0"):
        w.save_run(RunRecord(run_id, "screen", D1, T).finish(T))
    pending = [("DDD", "QUALIFIED", 1.0, None), ("AAA", "WATCH", 2.0, 0.5)]
    write_run(w, D1, "r9", "site", "alpha", pending, T + timedelta(hours=2), pending=True)
    return backend


def _wanted(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["rank", "instrument_id"], kind="stable").reset_index(drop=True)
    return ordered[["instrument_id", "decision", "score", "rank", "tie_break", "config_version"]]


@pytest.mark.parametrize("own", [None, "r9"])
def test_the_run_rows_of_every_screener_are_what_the_merge_gave(
    either: Backend, own: str | None
) -> None:
    reader = StoreReader(either) if own is None else StoreReader(either).including(own)
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("me"), D1)
    merged = reader.table("results/rule_screen", D1)
    assert merged is not None
    keys = [("site", "alpha"), ("me", "beta"), ("site", "beta")]
    found = load_latest_runs(ctx, keys)
    assert found[("site", "alpha")].run is not None
    assert found[("site", "alpha")].run.run_id == ("r9" if own else "r1")  # type: ignore[union-attr]
    for (owner, config), latest in found.items():
        run = latest.run
        assert run is not None
        rows = merged[(merged["user_id"] == owner) & (merged["config_id"] == config)]
        _, want = last_run_rows(rows)
        pd.testing.assert_frame_equal(_wanted(run_rows(ctx, run)), _wanted(want))


def test_a_run_that_is_not_the_newest_reads_its_own_rows(either: Backend) -> None:
    ctx = open_context(StoreReader(either), MemoryConfigStore({}), UserContext("me"), D1)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None and run.run_id == "r1"
    old = replace(run, run_id="r0")
    own = either.tables.read_run("results/rule_screen", D1, "r0")
    assert own is not None
    pd.testing.assert_frame_equal(_wanted(run_rows(ctx, old)), _wanted(own))
    assert len(run_rows(ctx, old)) == 4 and len(run_rows(ctx, run)) == 2


def _before_summaries(reader: StoreReader, owner: str, config: str) -> tuple[Any, ...] | None:
    """What the run's frame-derived fields were when every config's rows were held whole: the
    merged partition cut to the config, by the latest-run rule."""
    merged = reader.table("results/rule_screen", D1)
    assert merged is not None
    rows = merged[(merged["user_id"] == owner) & (merged["config_id"] == config)]
    if rows.empty:
        return None
    last, mine = last_run_rows(rows)
    counts = mine["decision"].astype(str).value_counts()
    ordered = sorted(counts.items(), key=lambda dn: (-int(dn[1]), str(dn[0])))
    regime = mine["regime"].dropna() if "regime" in mine.columns else pd.Series(dtype=str)
    return (
        str(last["run_id"]),
        pd.Timestamp(last["knowledge_ts"]).to_pydatetime(),
        int(last["config_version"]),
        tuple((str(d), int(n)) for d, n in ordered),
        sum(int(n) for d, n in counts.items() if is_picked(str(d))),
        int(counts.get(runs.PAUSED, 0)),
        str(regime.iloc[0]) if not regime.empty else None,
    )


@pytest.mark.parametrize("view", ["committed", "own", "restated"])
def test_the_run_summaries_are_what_the_whole_rows_gave(either: Backend, view: str) -> None:
    if view == "restated":  # a run that rewrites the partition: the merge starts from it
        frame = stamped(
            [{"instrument_id": "EQ:AAA", "user_id": "site", "config_id": "alpha",
              "config_version": 1, "config_hash": "h", "decision": "WATCH", "score": 1.0,
              "rank": 1, "tie_break": None, "flags": "", "reasons": "", "failed": "",
              "near_missed": "", "missing": "", "regime": "CALM"}],
            D1, "rr", T + timedelta(hours=3),
        )  # fmt: skip
        either.tables.write("results/rule_screen", D1, "rr", frame, restates=True)
    reader = StoreReader(either).including("r9") if view == "own" else StoreReader(either)
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("me"), D1)
    keys = [("site", "alpha"), ("me", "beta"), ("site", "beta")]
    found = load_latest_runs(ctx, keys)
    for owner, config in keys:
        want = _before_summaries(reader, owner, config)
        run = found[(owner, config)].run
        if want is None:
            assert run is None
            continue
        assert run is not None
        assert (
            run.run_id,
            run.knowledge_ts,
            run.config_version,
            tuple((d.decision, d.count) for d in run.decisions),
            run.picked,
            run.paused,
            run.regime,
        ) == want


# ---------------------------------------------------------------- frozen runs
# A run's read object from its frozen ``results/screen_runs`` row equals the one recounted from
# ``results/rule_screen`` (owner decision 2026-10-22, "Screener changes"); a session without the
# table is the old path, never ``NOT_RUN``; the frozen path reads no row of any run.

KEYS = [("site", "alpha"), ("me", "beta"), ("site", "beta"), ("me", "gamma")]
SCREEN_RUNS = "screen_runs"


def _decisions(ctx: ReadContext, run_id: str, owner: str, config: str) -> dict[str, str]:
    stored = ctx.reader.read_run("results/rule_screen", ctx.session.date, run_id)
    assert stored is not None
    mine = stored[(stored["user_id"] == owner) & (stored["config_id"] == config)]
    return {str(i): str(d) for i, d in zip(mine["instrument_id"], mine["decision"], strict=True)}


def freeze(
    backend: MemoryBackend, days: tuple[date, ...] = (D0, D1), skip: tuple[str, ...] = ()
) -> None:
    """Write the ``screen_runs`` row of every run of the store, as the writer would have: from
    the rows, the previous run being the config's newest in the previous stored session."""
    reader = StoreReader(backend)
    writer = StoreWriter(backend)
    for day in days:
        now = at_session(context(reader, user="admin"), day)
        keys = [("site", "alpha"), ("site", "beta"), ("me", "beta"), ("me", "gamma")]
        for owner, config in keys:
            found = latest_run(now, owner, config).run
            if found is None or (config in skip and owner == "site"):
                continue
            decisions = _decisions(now, found.run_id, owner, config)
            before = load_previous_run(now, found)
            then = (
                None
                if before is None
                else _decisions(at_session(now, before.session), before.run_id, owner, config)
            )
            new, dropped = (None, None) if then is None else change_counts(decisions, then)
            counts = {d.decision: d.count for d in found.decisions}
            row = {
                "user_id": owner, "config_id": config, "config_hash": "h",
                "config_version": found.config_version, "rows": len(decisions),
                "passed": found.picked, "picked": found.picked, "paused": found.paused,
                "decision_names": sorted(counts),
                "decision_counts": [counts[d] for d in sorted(counts)],
                "regime": found.regime, "size_multiplier": 1.0,
                "previous_run_id": None if before is None else before.run_id,
                "previous_session": None if before is None else before.session,
                "previous_version": None if before is None else before.config_version,
                "new_picks": new, "dropped": dropped,
            }  # fmt: skip
            frame = pd.DataFrame([row])
            for name in ("config_version", "previous_version", "new_picks", "dropped"):
                frame[name] = frame[name].astype("Int64")
            writer.write_result(
                SCREEN_RUNS, day, found.run_id, _stamp(frame, day, found.run_id, found.knowledge_ts)
            )


def _stamp(frame: pd.DataFrame, day: date, run_id: str, knowledge: Any) -> pd.DataFrame:
    frame["session_date"] = day
    frame["knowledge_ts"] = pd.Timestamp(knowledge)
    frame["source"] = "test"
    frame["run_id"] = run_id
    return frame


@pytest.fixture
def stores() -> tuple[StoreReader, StoreReader]:
    """The same screens twice: ``old`` has ``rule_screen`` only, ``new`` its frozen rows too
    (a gated, PAUSED run of ``alpha`` included)."""
    old, new = screens_store(), screens_store()
    for backend in (old, new):
        write_gated(backend)
    freeze(new)
    return StoreReader(old), StoreReader(new)


def _bare(run: Any) -> Any:
    return None if run is None else replace(run, frozen=None)


@pytest.mark.parametrize("user", ["me", "admin", "trader"])
def test_the_frozen_run_is_the_recounted_run(
    stores: tuple[StoreReader, StoreReader], user: str
) -> None:
    old, new = (context(r, user=user) for r in stores)
    before, after = load_latest_runs(old, KEYS), load_latest_runs(new, KEYS)
    assert after[("site", "alpha")].run is not None and after[("site", "alpha")].run.frozen
    for key in KEYS:
        assert _bare(after[key].run) == before[key].run  # picked, paused, decisions, version
        assert after[key].not_run == before[key].not_run  # the NOT_RUN cause, role-scoped
    alpha = after[("site", "alpha")].run
    assert alpha is not None and (alpha.picked, alpha.paused) == (1, 2)  # a PAUSED pick
    gamma = after[("me", "gamma")].not_run
    assert gamma is not None and gamma.code is UnknownCode.NOT_RUN


def test_the_frozen_changes_equal_the_recounted_changes(
    stores: tuple[StoreReader, StoreReader],
) -> None:
    old, new = (context(r) for r in stores)
    for key in [("site", "alpha"), ("me", "beta")]:  # a previous run, and a first run
        was, now = latest_run(old, *key).run, latest_run(new, *key).run
        assert was is not None and now is not None
        recount, frozen = results.load_run_changes(old, was), results.load_run_changes(new, now)
        assert frozen == recount
        summary = results.load_change_summary(new, now)
        assert (summary.previous_session, summary.counts) == (
            recount.previous_session,
            recount.counts,
        )
    first = latest_run(new, "me", "beta").run
    assert first is not None and first.frozen is not None
    assert first.frozen.new_picks is None  # no previous run: null, never 0
    assert results.load_change_summary(new, first).counts == ()


def test_a_result_page_and_a_personal_field_are_the_same_either_way(
    stores: tuple[StoreReader, StoreReader],
) -> None:
    for user in ("me", "trader"):  # `me` holds the personal licence, `trader` does not
        pages = []
        for reader in stores:
            ctx = context(reader, user=user)
            run = latest_run(ctx, "site", "alpha").run
            assert run is not None
            pages.append(results.load_result_page(ctx, run, ResultQuery(change="dropped")))
        assert pages[0] == pages[1]
        assert pages[0].results  # the PAUSED BBB dropped against the previous run


def test_definition_changed_is_the_previous_version_differing(
    stores: tuple[StoreReader, StoreReader],
) -> None:
    run = latest_run(context(stores[1]), "site", "alpha").run
    assert run is not None and run.frozen is not None
    assert run.definition_changed is False
    assert replace(run, config_version=2).definition_changed is True
    assert replace(run, frozen=None).definition_changed is None


def test_a_session_without_screen_runs_is_the_old_path_never_not_run(
    stores: tuple[StoreReader, StoreReader],
) -> None:
    ctx = context(stores[0])
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None and run.frozen is None and run.picked == 1
    assert load_latest_runs(ctx, [("site", "alpha")])[("site", "alpha")].not_run is None
    assert results.load_change_summary(ctx, run) == results.load_run_changes(ctx, run)


def test_the_frozen_path_reads_no_row_of_any_run(
    stores: tuple[StoreReader, StoreReader], monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = stores[1]
    read: list[str] = []
    for name in ("read_run", "read_latest_runs", "table", "table_range"):
        real = getattr(reader, name)

        def counting(table: str, *args: Any, _real: Any = real, **kwargs: Any) -> Any:
            read.append(table)
            return _real(table, *args, **kwargs)

        monkeypatch.setattr(reader, name, counting)
    ctx = context(reader)
    found = load_latest_runs(ctx, KEYS[:3])  # every one has a frozen row
    for key in KEYS[:3]:
        run = found[key].run
        if run is not None:
            results.load_change_summary(ctx, run)
    assert read and set(read) == {f"results/{SCREEN_RUNS}"}
    assert RULE_SCREEN not in read


def test_a_config_with_no_frozen_row_in_a_session_that_has_some_is_recounted_not_not_run() -> None:
    backend = screens_store()
    freeze(backend, skip=("alpha",))  # a screen_runs partition; alpha has a rule_screen run only
    ctx = context(StoreReader(backend))
    found = load_latest_runs(ctx, [("site", "alpha"), ("me", "beta"), ("me", "nobody")])
    alpha = found[("site", "alpha")].run
    assert alpha is not None and alpha.frozen is None and alpha.run_id == "r1"
    assert found[("me", "beta")].run is not None and found[("me", "beta")].run.frozen
    nobody = found[("me", "nobody")].not_run  # neither table has it
    assert nobody is not None and nobody.code is UnknownCode.NOT_RUN


def test_the_common_path_probes_no_rule_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = screens_store()
    freeze(backend)
    reader = StoreReader(backend)
    ctx = context(reader)  # resolving the session probes tables; the loader is what is counted
    seen: list[str] = []
    real = reader.has_partition
    monkeypatch.setattr(reader, "has_partition", lambda t, *a: (seen.append(t), real(t, *a))[1])
    load_latest_runs(ctx, [("site", "alpha"), ("me", "beta")])
    assert RULE_SCREEN not in seen
