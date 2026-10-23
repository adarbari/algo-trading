"""``screen-values-recluster``: older rule-screen files are rewritten sorted in small row groups
under the same run ids and ``knowledge_ts``, the rows unchanged; a second run writes nothing, a
``--limit`` run is finished by running it again, and a failure mid-run leaves every file of the
run as it was (ADR 0022)."""

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.screens import screen_values_recluster as task
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import (
    T0,
    make_unclustered,
    screen_rows,
    screen_values_rows,
    stamped,
)

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)  # the task's clock: never a row's knowledge_ts
DAYS = (date(2026, 10, 1), date(2026, 10, 2))
TABLES = ("rule_screen", "rule_screen_values")
RUNS = {DAYS[0]: ["a1", "a2"], DAYS[1]: ["b1"]}
INSTRUMENTS = 3_000  # x 3 values rows = 9,000: two row groups once clustered


class Store:
    """A local store whose rule-screen files were all written before clustering."""

    def __init__(self, root: Path) -> None:
        self.root = root / "data"
        self.writer = StoreWriter(LocalBackend(self.root))
        self.reader = StoreReader(self.writer._backend)
        for day, runs in RUNS.items():
            for n, run in enumerate(runs):
                known = T0 + timedelta(hours=n)
                self.writer.write_result(
                    "rule_screen", day, run, stamped(screen_rows(INSTRUMENTS), day, run, known)
                )
                rows = screen_values_rows(INSTRUMENTS)
                self.writer.write_result(
                    "rule_screen_values", day, run, stamped(rows, day, run, known)
                )
            for name in TABLES:
                make_unclustered(self.root / "tables" / "results" / name / f"date={day}")

    def files(self) -> int:
        return len(list((self.root / "tables").rglob("run=*.parquet")))

    def visible(self) -> dict[tuple[str, date], dict[str, datetime]]:
        return {
            (name, day): self.writer.run_visible_from(f"results/{name}", day)
            for name in TABLES
            for day in DAYS
        }

    def layouts(self) -> dict[tuple[str, date, str], bool]:
        return {
            (name, day, run): laid
            for name in TABLES
            for day in DAYS
            for run, laid in self.writer.run_layouts(f"results/{name}", day).items()
        }

    def frames(self) -> dict[tuple[str, date, str], pd.DataFrame]:
        found = {}
        for name in TABLES:
            for day, runs in RUNS.items():
                for run in runs:
                    frame = self.reader.read_run(f"results/{name}", day, run)
                    assert frame is not None
                    found[(name, day, run)] = frame

        return found

    def recluster(self, limit: int | None = None, **window: date) -> Any:
        ctx = task_ctx(self.writer, self.reader, clock=lambda: NOW)
        return task.recluster_screen_values(ctx, window.get("start"), window.get("end"), limit)


def same_rows(before: pd.DataFrame, after: pd.DataFrame) -> None:
    keys = [c for c in ("instrument_id", "criterion_id") if c in before]
    pd.testing.assert_frame_equal(
        before.sort_values(keys).reset_index(drop=True),
        after.sort_values(keys).reset_index(drop=True),
    )


def test_every_old_file_is_rewritten_clustered_with_the_same_rows_and_stamps(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path)
    before = store.frames()
    assert not any(store.layouts().values())
    record = store.recluster()
    assert record.status is RunStatus.COMPLETE, record.stats
    assert all(store.layouts().values())
    after = store.frames()
    for key, frame in before.items():
        same_rows(frame, after[key])
        assert (after[key]["knowledge_ts"] == frame["knowledge_ts"]).all()  # never "now"
        assert set(after[key]["run_id"]) == {key[2]}  # the same run id
    assert record.stats["reclustered"] == 3


def test_a_second_run_finds_nothing_to_write(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.recluster()
    index = {
        p: p.read_bytes() for p in (store.root / "tables").rglob("_runs.json")
    }  # every partition's index
    again = store.recluster()
    assert again.stats.get("reclustered", 0) == 0
    assert again.stats["already_clustered"] == 6  # three runs x two tables
    assert {p: p.read_bytes() for p in index} == index


def test_a_limit_stops_early_and_running_again_finishes(tmp_path: Path) -> None:
    store = Store(tmp_path)
    first = store.recluster(limit=1)
    assert first.status is RunStatus.PARTIAL and first.stats["not_reached"] == 2
    assert sum(store.layouts().values()) == 2  # one run, both tables
    second = store.recluster()
    assert second.status is RunStatus.COMPLETE and second.stats["reclustered"] == 2
    assert all(store.layouts().values())


def test_the_window_bounds_the_sessions_rewritten(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.recluster(start=DAYS[1], end=DAYS[1])
    done = {key[1] for key, laid in store.layouts().items() if laid}
    assert done == {DAYS[1]}


def test_a_failed_publish_leaves_the_run_exactly_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path)
    before = store.frames()
    real = store.writer.write_result
    calls: list[str] = []

    def failing(name: str, *args: Any, **kwargs: Any) -> None:
        calls.append(name)
        if len(calls) == 2:  # the run's second table: after its first was staged
            raise OSError("disk full")
        real(name, *args, **kwargs)

    monkeypatch.setattr(store.writer, "write_result", failing)
    record = store.recluster()
    assert record.status is not RunStatus.COMPLETE and record.stats["reclustered"] == 2
    stuck = {key for key, laid in store.layouts().items() if not laid}
    assert stuck == {(name, DAYS[0], "a1") for name in TABLES}  # neither table of the run moved
    after = store.frames()
    for name in TABLES:
        pd.testing.assert_frame_equal(after[(name, DAYS[0], "a1")], before[(name, DAYS[0], "a1")])
    assert store.recluster().stats["reclustered"] == 1  # the next run retries it


def test_a_value_changed_on_the_way_is_never_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mismatch is found before the commit: the publish aborts, the run is as it was."""
    store = Store(tmp_path)
    before, seen = store.frames(), store.visible()
    real = store.writer.write_result

    def altering(name: str, day: date, run: str, frame: pd.DataFrame, **kwargs: Any) -> None:
        if name == "rule_screen_values" and run == "a1":
            frame = frame.copy()
            frame["value_num"] = frame["value_num"] + 1.0  # a value changed on the way
        real(name, day, run, frame, **kwargs)

    monkeypatch.setattr(store.writer, "write_result", altering)
    record = store.recluster()
    assert record.status is not RunStatus.COMPLETE and record.stats["reclustered"] == 2
    assert not store.layouts()[("rule_screen_values", DAYS[0], "a1")]  # not rewritten
    assert not store.layouts()[("rule_screen", DAYS[0], "a1")]  # nor its sibling table
    after = store.frames()
    for key, frame in before.items():
        if key[2] == "a1":
            pd.testing.assert_frame_equal(after[key], frame)  # exactly the old rows
    assert store.visible() == seen and store.writer.backend.tables.pending_runs() == []


def test_the_commit_keeps_the_run_visible_from_when_it_was(tmp_path: Path) -> None:
    store = Store(tmp_path)
    seen = store.visible()
    assert store.recluster().status is RunStatus.COMPLETE
    assert store.visible() == seen  # neither earlier nor later, whatever the rows' stamps


def old_files(store: Store) -> None:
    """Make every file old enough for the grace and the sweep (a minute and more later)."""
    for path in (store.root / "tables").rglob("run=*.parquet"):
        os.utime(path, (0, 0))


def test_the_old_file_of_a_reclustered_run_is_trimmed_and_swept_after_the_grace(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path)
    assert store.recluster().stats.get("trimmed", 0) == 0  # too young: its readers may be on it
    assert store.files() == 2 * 6  # three runs x two tables, the old and the new file each
    old_files(store)
    again = store.recluster()
    assert again.stats.get("reclustered", 0) == 0 and again.stats["trimmed"] == 6
    assert store.files() == 6  # exactly one file per run and table
    assert store.recluster().stats.get("trimmed", 0) == 0  # idempotent
    assert all(store.layouts().values())
    for frame in store.frames().values():
        assert len(frame) > 0


def test_a_version_a_pin_may_read_is_kept_until_the_pin_goes(tmp_path: Path) -> None:
    store = Store(tmp_path)
    tables = store.writer.backend.tables
    tables.pin("release", tables.visible_seq())  # a serving release (ADR 0077) before the rewrite
    store.recluster()
    old_files(store)
    store.recluster()
    assert store.files() == 2 * 6  # the version the release reads stays
    tables.unpin("release")
    store.recluster()
    assert store.files() == 6
