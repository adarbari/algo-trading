"""``screen-runs-backfill``: the run objects of runs stored before them equal what the live path
frames for the same runs, are written once, at the original ``knowledge_ts``, resumably, and a
disagreement with ``rule_screen`` is reported, never overwritten (ADR 0077 amendment (c))."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.configs import resolve_config
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.screening import run as run_module
from algotrade.services.screening.run import run_screener
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.screens import screen_runs_backfill as task
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import T0
from tests.unit.services.screening.test_rule_screens import DAY, configs, seeded
from tests.unit.services.screening.test_screen_runs import PREVIOUS, previous_session

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)  # the backfill's clock: never a row's knowledge_ts
T1 = T0 + timedelta(days=1)
OBJECTS = ("screen_runs", "screen_picks")
Live = dict[tuple[date, str], dict[str, pd.DataFrame]]


def table(reader: Any, name: str, day: date = DAY) -> pd.DataFrame:
    frame = reader.table(f"results/{name}", day)
    assert frame is not None, (name, day)
    return frame


class Legacy:
    """A store whose runs were screened before ``screen_runs`` / ``screen_picks`` existed, and the
    frames the live path framed for them (captured, then dropped from the publish)."""

    def __init__(self, user_run: bool = False, version_unknown: bool = False) -> None:
        self.reader, self.writer = seeded()
        previous_session(self.writer)
        self.live: Live = {}
        self.ids: dict[tuple[date, str], str] = {}
        real = run_module.rule_frames

        def legacy_frames(result: Any, stamp: Any, lineage: Any = None) -> dict[str, Any]:
            frames = real(result, stamp, lineage)
            self.live[(stamp.session_date, stamp.user_id)] = {k: frames[k].copy() for k in OBJECTS}
            for name in OBJECTS:
                del frames[name]
            if version_unknown:
                frames["rule_screen"]["config_version"] = pd.array([None], dtype="Int64").repeat(
                    len(frames["rule_screen"])
                )
            return frames

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(run_module, "rule_frames", legacy_frames)
            users = ["site", "alice"] if user_run else ["site"]
            for day, now in ((PREVIOUS, T0), (DAY, T1)):
                for user in users:
                    config = resolve_config(configs(), "big_liquid", UserContext(user))
                    out = run_screener(
                        self.reader, self.writer, config, day, now=now, held=HARNESS_ALL
                    )
                    self.ids[(day, user)] = out.run_id
                    if version_unknown:
                        record = self.writer.load_run(out.run_id)
                        assert record is not None
                        record.stats.pop("config_version")
                        self.writer.save_run(record)

    def ctx(self) -> TaskContext:
        return task_ctx(self.writer, StoreReader(self.writer._backend), clock=lambda: NOW)

    def backfill(self, limit: int | None = None, **window: date) -> Any:
        return task.backfill_screen_runs(self.ctx(), window.get("start"), window.get("end"), limit)


def frame_of(reader: Any, name: str, day: date, run_id: str) -> pd.DataFrame:
    found = reader.read_run(f"results/{name}", day, run_id)
    assert found is not None
    return found.sort_values("instrument_id" if "picks" in name else "run_id").reset_index(
        drop=True
    )


def nulls_alike(frame: pd.DataFrame) -> pd.DataFrame:
    """Missing values as None whatever the column's dtype (a stored frame reads NaN back)."""
    return frame.astype(object).where(frame.notna(), None)


def test_backfilled_rows_equal_the_live_framed_rows_of_the_same_runs() -> None:
    """Equivalence (both sessions, so the frozen changes against the previous run too)."""
    legacy = Legacy()
    assert legacy.reader.table("results/screen_runs", DAY) is None  # before: nothing framed
    record = legacy.backfill()
    assert record.status is RunStatus.COMPLETE, record.stats
    for (day, user), frames in legacy.live.items():
        run_id = legacy.ids[(day, user)]
        for name in OBJECTS:
            stored = frame_of(legacy.reader, name, day, run_id)
            live = frames[name].sort_values("instrument_id" if "picks" in name else "run_id")
            live = live.assign(run_id=run_id).reset_index(drop=True)
            pd.testing.assert_frame_equal(nulls_alike(stored), nulls_alike(live), check_dtype=False)
    (row,) = table(legacy.reader, "screen_runs").to_dict("records")
    assert (row["new_picks"], row["dropped"]) == (1, 1) and row["previous_session"] == PREVIOUS


def test_a_second_run_writes_nothing_new() -> None:
    legacy = Legacy()
    first = legacy.backfill()
    seq = legacy.reader.visible_seq()
    second = legacy.backfill()
    assert legacy.reader.visible_seq() == seq  # no publish at all
    assert first.stats["framed"] == 2 and "framed" not in second.stats
    assert second.stats["already_framed"] == 2 and second.status is RunStatus.COMPLETE
    assert len(table(legacy.reader, "screen_runs")) == 1  # one row per run, not duplicated


def test_the_original_knowledge_ts_is_kept_never_now() -> None:
    """Point in time: the row is knowable from the run's own time, and a read as of before the
    run does not see it."""
    legacy = Legacy()
    legacy.backfill()
    for name in (*OBJECTS, "rule_screen"):
        assert set(table(legacy.reader, name)["knowledge_ts"]) == {pd.Timestamp(T1)}, name
    assert legacy.reader.table("results/screen_runs", DAY, as_of=T1 - timedelta(hours=1)) is None
    assert legacy.reader.table("results/screen_runs", DAY, as_of=T1) is not None
    assert NOW > T1  # the clock the backfill ran on is later than every stamp it wrote


def test_a_run_cut_short_is_finished_by_running_again() -> None:
    legacy = Legacy()
    first = legacy.backfill(limit=1)
    assert first.status is RunStatus.PARTIAL and first.stats["framed"] == 1
    assert first.stats["not_reached"] == 1 and first.stats["unframed_count"] == 0
    assert legacy.reader.table("results/screen_runs", DAY) is None  # the oldest session first
    assert legacy.reader.table("results/screen_runs", PREVIOUS) is not None
    second = legacy.backfill()
    assert second.status is RunStatus.COMPLETE
    assert (second.stats["framed"], second.stats["already_framed"]) == (1, 1)
    whole = Legacy()
    whole.backfill()
    for day in (PREVIOUS, DAY):
        cut = table(legacy.reader, "screen_runs", day).drop(columns="run_id")
        full = table(whole.reader, "screen_runs", day).drop(columns="run_id")
        pd.testing.assert_frame_equal(cut, full, check_dtype=False)
    assert second.stats["progress"]["sessions_done"] == 2  # progress saved to the job record


def test_the_window_limits_the_sessions() -> None:
    legacy = Legacy()
    record = legacy.backfill(start=DAY, end=DAY)
    assert record.stats["sessions"] == 1 and record.stats["framed"] == 1
    assert legacy.reader.table("results/screen_runs", PREVIOUS) is None


def test_a_user_run_keeps_its_user_and_is_compared_with_that_users_previous_run() -> None:
    legacy = Legacy(user_run=True)
    legacy.backfill()
    runs = table(legacy.reader, "screen_runs")
    assert sorted(runs["user_id"]) == ["alice", "site"]
    picks = table(legacy.reader, "screen_picks")
    assert set(picks["user_id"]) == {"alice", "site"}
    for _, row in runs.iterrows():
        before = legacy.ids[(PREVIOUS, row["user_id"])]
        assert row["previous_run_id"] == before  # never the other user's run
        live = legacy.live[(DAY, row["user_id"])]["screen_runs"].iloc[0]
        assert row["new_picks"] == live["new_picks"] and row["dropped"] == live["dropped"]
    wanted = table(legacy.reader, "rule_screen")
    assert set(picks["user_id"]) <= set(wanted["user_id"])


def test_an_unknown_version_is_null_with_a_reason() -> None:
    legacy = Legacy(version_unknown=True)
    record = legacy.backfill()
    assert pd.isna(table(legacy.reader, "screen_runs").iloc[0]["config_version"])
    assert record.stats["version_unknown_count"] == 2
    assert "no version" in record.stats["version_unknown"][0]


def test_a_run_record_that_disagrees_with_the_rows_is_reported_not_framed() -> None:
    legacy = Legacy()
    record = legacy.writer.load_run(legacy.ids[(DAY, "site")])
    assert record is not None
    record.stats["summary"]["passed"] = 99
    legacy.writer.save_run(record)
    done = legacy.backfill()
    assert done.status is RunStatus.PARTIAL and done.stats["mismatch"] == 1
    assert "differs from rule_screen" in done.stats["mismatches"][0]
    assert legacy.reader.table("results/screen_runs", DAY) is None  # nothing written for it
    assert legacy.reader.table("results/screen_runs", PREVIOUS) is not None
    assert done.stats["unframed_count"] == 1  # the acceptance check names the session


def test_a_framed_run_whose_counts_differ_is_reported_and_left_as_it_is() -> None:
    legacy = Legacy()
    legacy.backfill()
    run_id = legacy.ids[(DAY, "site")]
    wrong = frame_of(legacy.reader, "screen_runs", DAY, run_id).assign(rows=1, passed=0)
    # the same run's row, restated wrong, as a stale hand fix would leave it
    with legacy.writer.publishing(run_id, T1):
        legacy.writer.write_result("screen_runs", DAY, run_id, wrong, pending=True)
    done = legacy.backfill()
    assert done.status is RunStatus.PARTIAL and done.stats["mismatch"] == 1
    assert table(legacy.reader, "screen_runs").iloc[0]["rows"] == 1  # not overwritten


def test_the_task_is_registered_with_its_window_and_limit() -> None:
    from algotrade_ingestion.tasks.framework.registry import TASKS  # noqa: PLC0415

    spec = TASKS["screen-runs-backfill"]
    assert {p.name for p in spec.params} == {"session", "start", "end", "limit"}
    assert set(spec.tables) == {"results/screen_runs", "results/screen_picks"}
