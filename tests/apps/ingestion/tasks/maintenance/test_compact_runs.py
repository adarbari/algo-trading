"""``compact-runs`` (ADR 0078): a dry run writes nothing and reports the saving; a run compacts a
partition and sweeps what the swap superseded without a read noticing; it stops when the ingest
lock is held or the disk is under the floor, skips a partition it cannot compact exactly with the
reason, is a no-op the second time, and refuses a table the config does not list."""

import ctypes
import os
import sys
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.config.site.nightly import CompactionSettings
from algotrade.config.site.settings import load_nightly
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.jobs.exclusive import DEPLOY_LOCK, INGEST_LOCK, INGEST_TREE_LOCK
from algotrade.storage.backends import local
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.run_compaction import Budget, CompactionVerificationError
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.locks import held
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework import registry
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.maintenance import compact_runs
from algotrade_ingestion.tasks.maintenance.compact_runs import compact, lower_priority
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import T0, stamped

TABLE = "events/dividend"  # a merge-mode table
SESSION = date(2026, 10, 5)
DAYS = (date(2026, 10, 1), date(2026, 10, 2))


def _document(**keys: Any) -> dict[str, Any]:
    compaction = {"tables": [TABLE], "pause_seconds": 0, "sweep_grace_seconds": 0, **keys}
    return {"compaction": compaction, "resources": {"min_free_gb": 0}}


def _put(
    backend: LocalBackend, day: date, run: str, amounts: dict[str, float], k: int, **kw: Any
) -> None:
    ts = pd.Timestamp(day, tz="UTC")
    rows = [{"instrument_id": i, "ts": ts, "cash_amount": v} for i, v in amounts.items()]
    frame = stamped(rows, day, run, T0 + timedelta(hours=k))
    backend.tables.write(TABLE, day, run, frame, pending=True, **kw)
    backend.tables.commit_run(f"{run}", T0 + timedelta(days=30, hours=k))


@pytest.fixture
def ctx(tmp_path: Path) -> TaskContext:
    backend = LocalBackend(tmp_path / "data")
    backend.tables.swap_grace_s = 0.0  # a swap's old files may be swept at once
    base = {"EQ:A": 1.0, "EQ:B": 1.0, "EQ:C": 1.0}
    for n, day in enumerate(DAYS):
        for k in range(1, 5):  # four identical rewrites per partition: the middle two are redundant
            _put(backend, day, f"{day:%d}r{k}", base, 10 * n + k)
    configs = MemoryConfigStore({("site", "settings", "nightly"): _document()})
    return replace(task_ctx(StoreWriter(backend)), configs=configs)


def _files(ctx: TaskContext) -> list[tuple[str, int]]:
    root = ctx.writer.backend.tables.root  # type: ignore[attr-defined]
    return sorted((p.name, p.stat().st_size) for p in root.rglob("*.parquet"))


def _reads(ctx: TaskContext) -> list[Any]:
    out = []
    for day in DAYS:
        frame = ctx.reader.table(TABLE, day)
        assert frame is not None
        out.append(frame.drop(columns=["knowledge_ts", "run_id"]).to_dict("records"))
    return out


def _run(ctx: TaskContext, **kw: Any) -> dict[str, Any]:
    record = compact(ctx, SESSION, TABLE, sleep=lambda s: None, prioritise=lambda n: None, **kw)
    return dict(record.stats)


def test_settings_default_to_no_table_and_read_the_toml() -> None:
    assert load_nightly(MemoryConfigStore({})).compaction == CompactionSettings()
    assert CompactionSettings().tables == ()
    store = MemoryConfigStore({("site", "settings", "nightly"): _document(batch_size=3)})
    assert load_nightly(store).compaction.batch_size == 3


def test_a_dry_run_writes_nothing_and_reports_the_saving(ctx: TaskContext) -> None:
    before = _files(ctx)
    stats = _run(ctx, dry_run=True)
    assert _files(ctx) == before
    assert stats["compacted"] == 2 and stats["runs_dropped"] == 4
    assert stats["files_before"] == 8 and stats["files_after"] == 4  # r1 and the last run stay
    assert stats["saving_bytes"] == stats["bytes_before"] - stats["bytes_after"] > 0
    assert [p["session"] for p in stats["partitions"]] == [d.isoformat() for d in DAYS]  # type: ignore[union-attr]


def test_a_run_compacts_and_sweeps_and_reads_are_equal(ctx: TaskContext) -> None:
    reads, seq = _reads(ctx), ctx.reader.visible_seq()
    stats = _run(ctx)
    assert stats["compacted"] == 2 and stats["swept_files"] >= 4 and "stopped" not in stats
    assert len(_files(ctx)) == 4  # the first and the last run of each; the superseded are gone
    assert _reads(ctx) == reads
    assert ctx.reader.visible_seq() == seq  # no commit: every cache key stays


def test_the_second_run_finds_nothing_to_do(ctx: TaskContext) -> None:
    _run(ctx)
    after = _files(ctx)
    stats = _run(ctx)
    assert stats["compacted"] == 0 and stats["unchanged"] == 2 and _files(ctx) == after


def test_limit_stops_after_n_compacted_and_the_next_run_resumes(ctx: TaskContext) -> None:
    assert _run(ctx, limit=1)["compacted"] == 1
    assert _run(ctx)["compacted"] == 1  # only the other partition was left


def test_a_range_compacts_only_its_partitions(ctx: TaskContext) -> None:
    stats = _run(ctx, start=DAYS[1], end=DAYS[1])
    assert stats["compacted"] == 1 and stats["partitions"][0]["session"] == DAYS[1].isoformat()


def test_a_held_ingest_lock_stops_the_run_and_nothing_changes(ctx: TaskContext) -> None:
    before = _files(ctx)
    with held(ctx.writer.backend.lock(INGEST_LOCK)):
        record = compact(ctx, SESSION, TABLE, sleep=lambda s: None, prioritise=lambda n: None)
    assert record.status == RunStatus.PARTIAL
    assert "ingest lock is held" in record.stats["stopped"] and record.stats["compacted"] == 0
    assert _files(ctx) == before


def test_the_free_space_floor_is_checked_before_each_partition(ctx: TaskContext) -> None:
    ctx.writer.free_bytes = lambda: 10  # type: ignore[method-assign]
    configs = MemoryConfigStore(
        {("site", "settings", "nightly"): {**_document(), "resources": {"min_free_gb": 1}}}
    )
    low = replace(ctx, configs=configs)
    before = _files(ctx)
    stats = _run(low)
    assert "GB free" in stats["stopped"] and stats["compacted"] == 0 and _files(ctx) == before


def test_a_partition_it_cannot_compact_is_skipped_with_the_reason(ctx: TaskContext) -> None:
    backend = ctx.writer.backend
    assert isinstance(backend, LocalBackend)
    _put(backend, DAYS[0], "restate", {"EQ:A": 1.0}, 9, restates=True)  # a restating run
    stats = _run(ctx)
    assert stats["compacted"] == 1 and sum(stats["skipped"].values()) == 1
    assert "restat" in next(iter(stats["skipped"]))


def test_a_table_the_config_does_not_list_is_refused(ctx: TaskContext) -> None:
    with pytest.raises(ConfigurationError, match=r"not in nightly\.toml"):
        compact(ctx, SESSION, "events/other", sleep=lambda s: None, prioritise=lambda n: None)


def test_the_task_is_registered_with_its_flags() -> None:
    spec = registry.TASKS["compact-runs"]
    assert {p.name for p in spec.params} >= {"table", "start", "end", "limit", "dry_run"}
    assert next(p for p in spec.params if p.name == "table").required


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_task_saves_no_run_and_moves_no_cache_key(ctx: TaskContext, dry_run: bool) -> None:
    # a saved run record moves runs_generation, which every GraphQL response key holds
    seq, runs = ctx.reader.visible_seq(), ctx.reader.runs_generation()
    assert _run(ctx, dry_run=dry_run)["compacted"] == 2
    assert (ctx.reader.visible_seq(), ctx.reader.runs_generation()) == (seq, runs)


def test_a_held_deploy_lock_does_not_stop_the_run(ctx: TaskContext) -> None:
    # serving deploys run from the release tree (ADR 0079): a deploy must not block a compaction
    with held(ctx.writer.backend.lock(DEPLOY_LOCK)):
        record = compact(ctx, SESSION, TABLE, sleep=lambda s: None, prioritise=lambda n: None)
    assert "stopped" not in record.stats and record.stats["compacted"] == 2


def test_the_deploy_lock_stays_free_while_a_partition_is_compacted(ctx: TaskContext) -> None:
    seen: list[bool] = []

    def pause(_: float) -> None:
        with held(ctx.writer.backend.lock(DEPLOY_LOCK), wait=False) as taken:
            seen.append(taken)

    compact(ctx, SESSION, TABLE, sleep=pause, prioritise=lambda n: None)
    assert seen and all(seen)  # a deploy can start in the pauses


def test_the_ingest_tree_lock_is_held_for_the_whole_run(ctx: TaskContext) -> None:
    seen: list[bool] = []

    def pause(_: float) -> None:
        with held(ctx.writer.backend.lock(INGEST_TREE_LOCK), wait=False) as taken:
            seen.append(taken)

    compact(ctx, SESSION, TABLE, sleep=pause, prioritise=lambda n: None)
    assert seen and not any(seen)  # the ingest-tree sync cannot start in the pauses


def test_a_held_ingest_tree_lock_stops_the_run_before_any_change(ctx: TaskContext) -> None:
    before = _files(ctx)
    with held(ctx.writer.backend.lock(INGEST_TREE_LOCK)):
        record = compact(ctx, SESSION, TABLE, sleep=lambda s: None, prioritise=lambda n: None)
    assert "ingest-tree lock is held" in record.stats["stopped"] and _files(ctx) == before


def test_lower_priority_never_raises_and_asks_for_the_cpu_nice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    niced: list[int] = []
    monkeypatch.setattr(os, "nice", niced.append)
    monkeypatch.setattr(sys, "platform", "linux")
    lower_priority(10)
    assert niced == [10]
    monkeypatch.setattr(os, "nice", lambda n: (_ for _ in ()).throw(OSError("no")))
    lower_priority(10)  # swallowed
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ctypes, "CDLL", lambda *a, **k: (_ for _ in ()).throw(OSError("no libc")))
    lower_priority(0)  # the disk policy failing is swallowed too


def test_progress_has_one_flushed_line_per_partition_and_per_sweep(ctx: TaskContext) -> None:
    lines: list[str] = []
    compact(
        ctx, SESSION, TABLE, sleep=lambda s: None, prioritise=lambda n: None, progress=lines.append
    )
    partitions = [line for line in lines if line.startswith(f"compact-runs {DAYS[0].year}")]
    assert len(partitions) == 2 and "files 4 -> 2" in partitions[0] and " s" in partitions[0]
    assert [d.isoformat() in lines[1 + i] for i, d in enumerate(DAYS)] == [True, True]
    assert sum("sweep" in line for line in lines) == 1  # one batch


def test_the_default_progress_sink_writes_and_flushes_stderr(
    ctx: TaskContext, capsys: pytest.CaptureFixture[str]
) -> None:
    compact(ctx, SESSION, TABLE, sleep=lambda s: None, prioritise=lambda n: None, limit=1)
    assert f"compact-runs {DAYS[0]}: files" in capsys.readouterr().err


@pytest.fixture
def spent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partition budget of zero seconds (the config minimum is one): spent at once."""
    original = compact_runs.settings_of
    monkeypatch.setattr(
        compact_runs,
        "settings_of",
        lambda c: (replace(original(c)[0], partition_seconds=0.0), original(c)[1]),
    )


@pytest.mark.usefixtures("spent")
def test_a_partition_over_its_budget_is_skipped_and_nothing_changes(ctx: TaskContext) -> None:
    before, reads = _files(ctx), _reads(ctx)
    lines: list[str] = []
    stats = compact(
        ctx,
        SESSION,
        TABLE,
        sleep=lambda s: None,
        prioritise=lambda n: None,
        progress=lines.append,
    ).stats
    assert stats["skipped"] == {"verification over budget": 2} and stats["compacted"] == 0
    assert "stopped" not in stats  # the run goes on to the next partition
    assert _files(ctx) == before and _reads(ctx) == reads  # new files discarded, nothing swapped
    assert sum("verification over budget" in line for line in lines) == 2


def test_a_dry_run_is_plan_only_by_default_and_says_so(ctx: TaskContext) -> None:
    lines: list[str] = []
    stats = compact(
        ctx, SESSION, TABLE, dry_run=True, prioritise=lambda n: None, progress=lines.append
    ).stats
    assert stats["verified"] is False and any("plan only" in line for line in lines)


def test_a_verifying_dry_run_runs_the_verification_a_live_run_does(
    ctx: TaskContext, monkeypatch: pytest.MonkeyPatch
) -> None:

    calls: list[int] = []
    original = local.verify_plan
    monkeypatch.setattr(local, "verify_plan", lambda *a, **k: calls.append(1) or original(*a, **k))
    before = _files(ctx)
    lines: list[str] = []
    stats = compact(
        ctx,
        SESSION,
        TABLE,
        dry_run=True,
        verify=True,
        prioritise=lambda n: None,
        progress=lines.append,
    ).stats
    assert len(calls) == 2 and stats["verified"] is True and stats["compacted"] == 2
    assert any("plan and verify" in line for line in lines) and _files(ctx) == before


@pytest.mark.usefixtures("spent")
def test_a_verifying_dry_run_reports_a_partition_over_budget(ctx: TaskContext) -> None:
    stats = compact(
        ctx,
        SESSION,
        TABLE,
        dry_run=True,
        verify=True,
        prioritise=lambda n: None,
        progress=lambda line: None,
    ).stats
    assert stats["skipped"] == {"verification over budget": 2}


def test_the_task_has_a_verify_flag() -> None:
    assert "verify" in {p.name for p in registry.TASKS["compact-runs"].params}


def test_a_budget_spent_during_verification_discards_the_files_it_wrote(
    ctx: TaskContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter(range(10_000))  # every clock read is one second: planning fits, verifying does not
    monkeypatch.setattr(local, "Budget", lambda s: Budget(5.5, lambda: float(next(ticks))))
    before, reads = _files(ctx), _reads(ctx)
    stats = _run(ctx)
    assert stats["skipped"] == {"verification over budget": 2} and stats["compacted"] == 0
    assert _files(ctx) == before and _reads(ctx) == reads


def test_a_verification_error_skips_that_partition_and_the_run_continues(
    ctx: TaskContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    original, seen = local.verify_plan, []

    def flaky(*args: Any, **kw: Any) -> None:
        seen.append(1)
        if len(seen) == 1:
            raise CompactionVerificationError("values differ at None")
        original(*args, **kw)

    monkeypatch.setattr(local, "verify_plan", flaky)
    before = _files(ctx)
    lines: list[str] = []
    stats = compact(
        ctx, SESSION, TABLE, sleep=lambda s: None, prioritise=lambda n: None, progress=lines.append
    ).stats
    assert stats["compacted"] == 1 and "stopped" not in stats
    assert list(stats["skipped"]) == ["verification failed: values differ at None"]
    assert any("verification failed" in line for line in lines)
    after = {n for n, _ in _files(ctx)}
    assert {n for n, _ in before if DAYS[0].strftime("%d") in n} <= after  # first day untouched
