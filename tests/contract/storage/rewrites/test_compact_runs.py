"""``compact_runs`` (ADR 0078): a merge partition's runs are replaced by the rows that matter, and
no read can tell: the same values at every ``as_of`` and every pinned sequence, the same
``visible_seq`` / ``partition_seq`` / ``dates``. A partition it cannot compact exactly, or a
pending one, is left untouched; a commit landing meanwhile, or a crash, loses nothing."""

import os
import threading
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends import local as local_module
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.backends.runs import local_index, run_compaction
from algotrade.storage.backends.runs.run_selection import StaleSnapshotError
from algotrade.storage.tables.interfaces import Backend, PartitionBusyError
from tests.helpers.stored_frames import T0, stamped

DAY = date(2026, 10, 2)
TABLE = "events/dividend"
TS = pd.Timestamp(DAY, tz="UTC")
US = pd.Timedelta(microseconds=1)
STAMPS = ["knowledge_ts", "run_id"]


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


@pytest.fixture
def local(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path / "data")


def at(k: int) -> pd.Timestamp:
    return pd.Timestamp(T0 + timedelta(hours=k))


def put(
    backend: Backend,
    run: str,
    amounts: dict[str, float],
    k: int,
    extra: dict[str, str] | None = None,
    restates: bool = False,
    commit: bool = True,
    commit_hour: float | None = None,
) -> None:
    """Run ``run`` (known at hour ``k``, committed a day and ``k`` hours after T0) writing
    ``amounts``; ``extra`` adds a later column to the named rows."""
    rows = [
        {"instrument_id": i, "ts": TS, "cash_amount": v, **({"note": (extra or {}).get(i)})}
        for i, v in amounts.items()
    ]
    frame = stamped(rows, DAY, run, T0 + timedelta(hours=k))
    if extra is None:
        frame = frame.drop(columns="note")
    backend.tables.write(TABLE, DAY, run, frame, restates=restates, pending=True)
    if commit:
        hour = k if commit_hour is None else commit_hour
        backend.tables.commit_run(run, T0 + timedelta(days=1, hours=hour))


def history(backend: Backend) -> None:
    """Six runs: identical rewrites (r2, r4, r6), a revision and a new key (r3), a column
    added later (r5), and a last run that rewrites everything unchanged."""
    base = {"EQ:A": 1.0, "EQ:B": 1.0, "EQ:C": 1.0}
    put(backend, "r1", base, 1)
    put(backend, "r2", base, 2)
    put(backend, "r3", {"EQ:B": 2.0, "EQ:D": 1.0}, 3)
    put(backend, "r4", {"EQ:A": 1.0, "EQ:B": 2.0, "EQ:C": 1.0, "EQ:D": 1.0}, 4)
    put(backend, "r5", {"EQ:A": 1.0}, 5, extra={"EQ:A": "x"})
    put(backend, "r6", {"EQ:A": 1.0, "EQ:C": 1.0}, 6, extra={"EQ:A": "x", "EQ:C": None})


def cuts() -> list[pd.Timestamp | None]:
    commits = [pd.Timestamp(T0 + timedelta(days=1, hours=k)) for k in range(1, 7)]
    return [None, *commits, *(c - US for c in commits), commits[0] - timedelta(hours=1)]


def values(backend: Backend, cut: pd.Timestamp | None) -> list[dict[str, object]] | None:
    frame = backend.tables.read(TABLE, DAY, as_of=cut)
    if frame is None:
        return None
    frame = frame.drop(columns=STAMPS)
    if "note" in frame.columns:
        frame["note"] = frame["note"].astype(object).where(frame["note"].notna(), None)
    rows = frame.astype(object).where(frame.notna(), None).to_dict("records")
    return sorted(rows, key=lambda r: str(r["instrument_id"]))


def view(backend: Backend) -> dict[str, object]:
    return {
        "cuts": {str(c): values(backend, c) for c in cuts()},
        "visible_seq": backend.tables.visible_seq(),
        "partition_seq": backend.tables.partition_seq(TABLE, DAY, DAY),
        "dates": backend.tables.dates(TABLE),
    }


def files(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "data").rglob("*.parquet"))


def index_text(tmp_path: Path) -> str:
    return next((tmp_path / "data").rglob("_runs.json")).read_text()


def test_values_are_equal_at_every_cut_and_the_sequences_do_not_move(backend: Backend) -> None:
    history(backend)
    before = view(backend)
    report = backend.tables.compact_runs(TABLE, DAY)
    assert report.skipped is None and report.runs_dropped == 2
    assert report.files_after == report.files_before - report.runs_dropped
    assert view(backend) == before
    assert backend.tables.partition_runs(TABLE, DAY) == ["r1", "r3", "r5", "r6"]


def pinned(backend: Backend, upto: int) -> object:
    if isinstance(backend, LocalBackend):
        data = backend.tables._partition(TABLE, DAY, None, None, None, upto)
        frame = None if data is None else data.to_pandas()
    else:
        assert isinstance(backend, MemoryBackend)
        frame = backend.tables._read(TABLE, DAY, None, None, None, upto)
    if frame is None:
        return None
    frame = frame.drop(columns=STAMPS).astype(object)
    return sorted(frame.where(frame.notna(), None).to_dict("records"), key=str)


def test_a_read_pinned_at_an_old_sequence_has_the_same_values(backend: Backend) -> None:
    history(backend)

    seqs = range(0, backend.tables.visible_seq() + 1)
    before = [pinned(backend, upto) for upto in seqs]
    backend.tables.compact_runs(TABLE, DAY)
    assert [pinned(backend, upto) for upto in seqs] == before


def test_dry_run_reports_and_changes_nothing(backend: Backend, tmp_path: Path) -> None:
    history(backend)
    before = view(backend)
    seen = files(tmp_path) if isinstance(backend, LocalBackend) else None
    dry = backend.tables.compact_runs(TABLE, DAY, dry_run=True)
    assert dry.runs_dropped == 2 and dry.bytes_after < dry.bytes_before
    assert view(backend) == before
    if seen is not None:
        assert files(tmp_path) == seen
    assert backend.tables.compact_runs(TABLE, DAY).runs_dropped == dry.runs_dropped


def test_a_second_run_is_a_no_op(backend: Backend, tmp_path: Path) -> None:
    history(backend)
    backend.tables.compact_runs(TABLE, DAY)
    after = view(backend)
    index = index_text(tmp_path) if isinstance(backend, LocalBackend) else None
    again = backend.tables.compact_runs(TABLE, DAY)
    assert again.runs_dropped == 0 and again.skipped is None
    assert again.files_after == again.files_before and view(backend) == after
    if index is not None:
        assert index_text(tmp_path) == index


def test_a_pending_run_makes_it_raise_and_leaves_everything(
    backend: Backend, tmp_path: Path
) -> None:
    history(backend)
    put(backend, "busy", {"EQ:Z": 1.0}, 9, commit=False)
    before = view(backend)
    seen = files(tmp_path) if isinstance(backend, LocalBackend) else None
    index = index_text(tmp_path) if isinstance(backend, LocalBackend) else None
    with pytest.raises(PartitionBusyError):
        backend.tables.compact_runs(TABLE, DAY)
    assert view(backend) == before
    if seen is not None and index is not None:
        assert files(tmp_path) == seen and index_text(tmp_path) == index


def test_a_restating_run_skips_the_partition_untouched(backend: Backend, tmp_path: Path) -> None:
    history(backend)
    put(backend, "r7", {"EQ:A": 1.0, "EQ:B": 2.0}, 7, restates=True)
    before = view(backend)
    index = index_text(tmp_path) if isinstance(backend, LocalBackend) else None
    report = backend.tables.compact_runs(TABLE, DAY)
    assert report.skipped and "restates" in report.skipped and report.runs_dropped == 0
    assert view(backend) == before
    if index is not None:
        assert index_text(tmp_path) == index


def test_knowledge_order_unlike_visible_order_skips_the_partition(backend: Backend) -> None:
    put(backend, "late", {"EQ:A": 1.0}, 5)  # known at hour 5, committed first
    backend.tables.write(  # known at hour 1, committed after: selected before "late"
        TABLE,
        DAY,
        "early",
        stamped([{"instrument_id": "EQ:B", "ts": TS, "cash_amount": 1.0}], DAY, "early", at(1)),
        pending=True,
    )
    backend.tables.commit_run("early", T0 + timedelta(days=1, hours=9))
    before = view(backend)
    report = backend.tables.compact_runs(TABLE, DAY)
    assert report.skipped and "order" in report.skipped and view(backend) == before


def test_a_missing_partition_is_skipped(backend: Backend) -> None:
    assert backend.tables.compact_runs(TABLE, DAY).skipped == "no such partition"


def test_a_commit_between_the_plan_and_the_swap_aborts_the_swap(
    local: LocalBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(local)
    before = files(tmp_path)
    real = local.tables.commits.swap_runs

    def commit_then_swap(*args: object, **kwargs: object) -> bool:
        put(local, "r7", {"EQ:Q": 1.0}, 7)  # lands after the plan was made
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(local.tables.commits, "swap_runs", commit_then_swap)
    report = local.tables.compact_runs(TABLE, DAY)
    assert report.skipped == "the index moved" and report.runs_dropped == 0
    assert files(tmp_path) == sorted([*before, "run=r7.parquet"])  # the new files are gone
    assert local.tables.partition_runs(TABLE, DAY)[-1] == "r7"
    assert {r["instrument_id"] for r in values(local, None) or []} >= {"EQ:Q", "EQ:A"}
    monkeypatch.setattr(local.tables.commits, "swap_runs", real)
    assert local.tables.compact_runs(TABLE, DAY).runs_dropped >= 2  # and works afterwards


def test_a_crash_before_the_swap_leaves_orphans_the_sweep_removes(
    local: LocalBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(local)
    before, seen = view(local), files(tmp_path)

    def die(*args: object, **kwargs: object) -> bool:
        raise SystemExit("killed")

    monkeypatch.setattr(local.tables.commits, "swap_runs", die)
    monkeypatch.setattr(type(local.tables), "_discard", staticmethod(lambda *a: None))
    with pytest.raises(SystemExit):
        local.tables.compact_runs(TABLE, DAY)
    left = [f for f in files(tmp_path) if f not in seen]
    assert left and view(local) == before
    assert local.tables.sweep_orphans(TABLE, DAY) == 0  # too young to be sure
    for path in (tmp_path / "data").rglob("*~*.parquet"):
        os.utime(path, (0, 0))
    assert local.tables.sweep_orphans(TABLE, DAY) == len(left)
    assert files(tmp_path) == seen and view(local) == before


def test_a_crash_after_the_swap_leaves_superseded_files_the_sweep_removes(
    local: LocalBackend, tmp_path: Path
) -> None:
    history(local)
    before, seen = view(local), files(tmp_path)
    report = local.tables.compact_runs(TABLE, DAY)  # nothing deletes after the swap
    assert view(local) == before
    assert all(f in files(tmp_path) for f in seen)  # the superseded files are still there
    assert local.tables.sweep_orphans(TABLE, DAY) == 0  # spared for the grace period
    for path in (tmp_path / "data").rglob("*.parquet"):
        os.utime(path, (0, 0))  # two minutes later
    assert local.tables.sweep_orphans(TABLE, DAY) >= report.runs_dropped
    assert len(files(tmp_path)) == report.files_after and view(local) == before


def test_a_zero_grace_swap_can_be_swept_at_once(local: LocalBackend, tmp_path: Path) -> None:
    history(local)
    before = view(local)
    local.tables.swap_grace_s = 0.0
    report = local.tables.compact_runs(TABLE, DAY)
    assert local.tables.sweep_orphans(TABLE, DAY) >= report.runs_dropped
    assert len(files(tmp_path)) == report.files_after and view(local) == before


def test_a_concurrent_read_loop_never_errors_or_sees_other_values(
    local: LocalBackend,
) -> None:
    history(local)
    expected = values(local, None)
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader() -> None:
        try:
            while not stop.is_set():
                frame = local.tables.read_range(TABLE, DAY, DAY)
                assert frame is not None and len(frame) == len(expected or [])
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    try:
        assert local.tables.compact_runs(TABLE, DAY).runs_dropped == 2
    finally:
        stop.set()
        for t in threads:
            t.join()
    assert not errors and values(local, None) == expected


def test_a_failing_verification_swaps_nothing(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(backend)
    before = view(backend)

    def broken(*args: object, **kwargs: object) -> None:
        raise run_compaction.CompactionVerificationError("values differ")

    monkeypatch.setattr("algotrade.storage.backends.local.verify_plan", broken)
    monkeypatch.setattr("algotrade.storage.backends.memory.verify_plan", broken)
    with pytest.raises(run_compaction.CompactionVerificationError):
        backend.tables.compact_runs(TABLE, DAY)
    assert view(backend) == before
    assert backend.tables.partition_runs(TABLE, DAY) == [f"r{k}" for k in range(1, 7)]


def test_a_run_with_an_older_version_is_kept_so_a_pinned_read_retries(backend: Backend) -> None:
    base = {"EQ:A": 1.0}
    put(backend, "r1", base, 1)
    put(backend, "r2", base, 2)
    put(backend, "r2", base, 2, commit_hour=2.5)  # resumed: a second version, seq 3
    put(backend, "r3", {"EQ:A": 2.0}, 3, commit_hour=3)
    seqs = range(0, backend.tables.visible_seq() + 1)
    before = [pinned(backend, u) for u in seqs]
    backend.tables.compact_runs(TABLE, DAY)
    assert "r2" in backend.tables.partition_runs(TABLE, DAY)
    for upto, expected in zip(seqs, before, strict=True):
        try:
            assert pinned(backend, upto) == expected
        except StaleSnapshotError:
            assert upto < 3  # the read would retry at a fresh sequence


def test_an_error_after_the_index_write_loses_nothing(
    local: LocalBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(local)
    before = view(local)
    real = local.tables.commits.swap_runs

    def swap_then_die(*args: object, **kwargs: object) -> bool:
        real(*args, **kwargs)  # type: ignore[arg-type]
        raise KeyboardInterrupt

    monkeypatch.setattr(local.tables.commits, "swap_runs", swap_then_die)
    with pytest.raises(KeyboardInterrupt):
        local.tables.compact_runs(TABLE, DAY)
    assert view(local) == before and len(local.tables.partition_runs(TABLE, DAY)) == 4


def test_a_failing_utime_does_not_stop_the_swap(
    local: LocalBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(local)
    before = view(local)

    def broken(*args: object, **kwargs: object) -> None:
        raise PermissionError("utime")

    monkeypatch.setattr(local_index.os, "utime", broken)
    assert local.tables.compact_runs(TABLE, DAY).runs_dropped == 2
    assert view(local) == before


def test_a_history_copy_made_between_the_plan_and_the_swap_aborts_it(
    local: LocalBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(local)
    before, seen = view(local), files(tmp_path)
    real = local.tables.commits.swap_runs

    def copy_then_swap(*args: object, **kwargs: object) -> bool:
        (local.tables.root / TABLE / "_history").mkdir()
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(local.tables.commits, "swap_runs", copy_then_swap)
    report = local.tables.compact_runs(TABLE, DAY)
    assert report.skipped == "the table has a history copy"
    assert view(local) == before and files(tmp_path) == seen


@pytest.mark.parametrize("moment", ["plan", "verify"])
def test_a_commit_during_the_plan_or_between_verify_and_swap_swaps_nothing(
    local: LocalBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, moment: str
) -> None:
    """A writer committing while a worker (which holds no lock) is mid-way: no swap, no fresh
    file left, the reason reported, the commit intact, and the next pass compacts."""
    history(local)
    seen = files(tmp_path)
    name = "plan_compaction" if moment == "plan" else "verify_plan"
    real = getattr(local_module, name)

    def then_commit(*args: object, **kwargs: object) -> object:
        out = real(*args, **kwargs)
        monkeypatch.setattr(local_module, name, real)  # once
        put(local, "r7", {"EQ:Q": 1.0}, 7)
        return out

    monkeypatch.setattr(local_module, name, then_commit)
    report = local.tables.compact_runs(TABLE, DAY)
    assert report.skipped == "the index moved" and report.runs_dropped == 0
    assert files(tmp_path) == sorted([*seen, "run=r7.parquet"])  # no fresh file left
    assert local.tables.partition_runs(TABLE, DAY)[-1] == "r7"
    assert local.tables.compact_runs(TABLE, DAY).runs_dropped >= 2


def test_a_run_pending_at_the_swap_raises_and_leaves_no_fresh_file(
    local: LocalBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(local)
    seen, before = files(tmp_path), view(local)
    real = local_module.verify_plan

    def then_stage(*args: object, **kwargs: object) -> object:
        out = real(*args, **kwargs)
        monkeypatch.setattr(local_module, "verify_plan", real)
        put(local, "busy", {"EQ:Z": 1.0}, 9, commit=False)  # staged after the plan, uncommitted
        return out

    monkeypatch.setattr(local_module, "verify_plan", then_stage)
    with pytest.raises(PartitionBusyError):
        local.tables.compact_runs(TABLE, DAY)
    assert files(tmp_path) == sorted([*seen, "run=busy.parquet"])  # the fresh files were removed
    assert view(local) == before


def test_a_kept_file_gone_before_the_verify_read_skips_and_leaves_no_fresh_file(
    local: LocalBackend, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history(local)
    seen, before = files(tmp_path), view(local)
    real = local_module._read_file
    state = {"after_write": False}

    def vanish(path: Path, *args: object, **kwargs: object) -> object:
        if "~" in path.name:  # first read of a fresh (kept) file: the verify read
            state["after_write"] = True
        if state["after_write"]:
            raise FileNotFoundError(path)
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(local_module, "_read_file", vanish)
    report = local.tables.compact_runs(TABLE, DAY)
    assert report.skipped == "the partition changed while verifying"
    monkeypatch.setattr(local_module, "_read_file", real)
    assert files(tmp_path) == seen and view(local) == before
