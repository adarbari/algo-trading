from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens import results, runs
from algotrade.services.read.screens.runs import (
    DecisionCount,
    last_run_rows,
    latest_run,
    load_latest_runs,
    load_previous_run,
    picked_mask,
    run_rows,
)
from algotrade.services.read.values import UnknownCode
from algotrade.services.screening.rule_results import NOT_PICKED, is_picked
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
