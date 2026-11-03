"""The ``option-history-outcomes`` task (ADR 0088 decision 11, E5) over a synthetic history store:
rows are written through E4's one publisher with ``price_source = option_history`` and the
licence ``personal``, ``knowledge_ts`` the history import's instant; windows from the Cboe cutover
on are not written (the table's key has no price source); only the index underlyings and the named
symbols are chains; a batch is computed with no run open and published under ONE hold of the
ingest lock, none across two publishes; nothing starts or publishes inside the nightly window; a
coverage gap or a rule over a field with no rows fails the run before anything is written; a
re-run skips what is written."""

import dataclasses
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.templates import load_templates
from algotrade.config.site.nightly import NightlySettings
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import (
    close_time,
    previous_session,
    sessions_between,
    sessions_ending,
)
from algotrade.data import StoreReader
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.features.site import site_features
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade_ingestion.tasks.derived.paths.option_outcomes import TABLE, frame_and_publish
from algotrade_ingestion.tasks.derived.paths.wanted import positions_wanted
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.options_history import outcomes
from algotrade_ingestion.tasks.options_history.outcomes import (
    HistoryOutcomeOptions,
    Pacing,
    compute_history_outcomes,
    coverage_problems,
    history_ends,
    nightly_window,
)
from tests.apps.ingestion.tasks.derived.paths.test_option_outcomes import (
    OUTCOME,
    PERSONAL,
    PERSONAL_TABLE,
    TEMPLATES,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.option_history.store import imported_at, write_history
from tests.helpers.rollup_store import store
from tests.helpers.stored_frames import stamped
from tests.unit.config.edges.test_document import document
from tests.unit.config.edges.test_loading import PRESETS

END = date(2019, 8, 16)
DAYS = sessions_ending(END, 7)
EXPIRY = date(2019, 9, 20)
NOW = datetime(2026, 11, 4, 8, tzinfo=UTC)  # 00:00 pacific: outside the nightly window
NAMES = {
    "SPY": ("EQ:SPY", 290.0), "SPX": ("IDX:SPX", 2900.0), "ZZZ": ("EQ:ZZZ", 50.0),
}  # fmt: skip
STRIKES = (270.0, 280.0, 290.0, 300.0)


def _configs(**outcome: Any) -> MemoryConfigStore:
    doc = document(schedule="every_session", screeners=[], outcome={**OUTCOME, **outcome})
    docs = {
        **PRESETS,
        ("site", "edges", "drift"): doc,
        ("site", "positions", "templates"): TEMPLATES,
    }
    return MemoryConfigStore(docs)


@pytest.fixture(autouse=True)
def _no_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    real = site_features(FileConfigStore(REPO_ROOT / "config", local=False))
    monkeypatch.setattr(outcomes, "site_features", lambda _configs: real)
    monkeypatch.setattr(outcomes, "coverage_problems", lambda *a: [])


class World:
    def __init__(self, configs: MemoryConfigStore | None = None, days: list[date] | None = None):
        self.history = MemoryBackend()
        write_history(self.history, days or DAYS, NAMES, EXPIRY, strikes=STRIKES)
        self.writer, self.reader = store()
        self.configs = configs or _configs()
        self.now = NOW
        self.sleeps: list[float] = []

    def ctx(self) -> TaskContext:
        return dataclasses.replace(
            task_ctx(self.writer, clock=lambda: self.now), configs=self.configs
        )

    def pacing(self) -> Pacing:
        def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += timedelta(seconds=seconds)

        return Pacing(sleep=sleep, retry_seconds=1.0, attempts=3)

    def run(self, **options: Any) -> Any:
        opts = HistoryOutcomeOptions(start=DAYS[2], end=END, **options)
        return compute_history_outcomes(
            self.ctx(), END, opts, open_store=lambda url: self.history, pacing=self.pacing()
        )

    def rows(self) -> pd.DataFrame:
        parts = [self.reader.table(TABLE, d) for d in self.reader.dates(TABLE)]
        parts = [p for p in parts if p is not None]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def test_rows_are_history_priced_personal_and_known_when_the_import_wrote_them() -> None:
    world = World()
    record = world.run()
    assert record.status == RunStatus.COMPLETE, record.stats
    rows = world.rows()
    assert set(rows["price_source"]) == {"option_history"} and set(rows["licence"]) == {"personal"}
    assert set(rows["instrument_id"]) == {"EQ:SPY", "IDX:SPX"}  # ZZZ is no chain until #968
    assert (rows["outcome_status"] == "COMPLETE").all()
    row = rows[(rows["window_end"] == END) & (rows["instrument_id"] == "IDX:SPX")].iloc[0]
    assert pd.Timestamp(row["knowledge_ts"]) == pd.Timestamp(imported_at(END))
    assert pd.Timestamp(row["ts"]) == pd.Timestamp(close_time(sessions_ending(END, 3)[0]))


def test_a_window_entered_from_the_cboe_cutover_is_never_written() -> None:
    before = sessions_ending(previous_session(FIRST_CBOE_CHAIN_SESSION), 3)
    after = sessions_between(FIRST_CBOE_CHAIN_SESSION, FIRST_CBOE_CHAIN_SESSION + timedelta(days=6))
    only_after = World(days=after)
    with pytest.raises(ConfigurationError, match="no window"):
        history_ends(StoreReader(only_after.history), after[0], after[-1], [2])
    world = World(days=[*before, *after])
    opts = HistoryOutcomeOptions(start=before[0], end=after[-1])
    record = compute_history_outcomes(
        world.ctx(), after[-1], opts, open_store=lambda url: world.history, pacing=world.pacing()
    )
    assert record.status == RunStatus.COMPLETE, record.stats
    rows = world.rows()
    assert len(rows) and (rows["ts"] < pd.Timestamp(close_time(FIRST_CBOE_CHAIN_SESSION))).all()
    assert pd.to_datetime(rows["window_end"]).dt.date.max() == after[1]  # S = before[-1], hold 2


def test_the_symbols_option_names_other_chains() -> None:
    world = World()
    world.run(symbols=("ZZZ",))
    assert set(world.rows()["instrument_id"]) == {"EQ:ZZZ", "IDX:SPX"}


def test_each_batch_is_computed_with_no_run_open_and_published_under_one_ingest_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    events: list[str] = []
    backend = world.writer.backend
    real_lock = backend.lock

    class Spy:
        def __init__(self, name: str):
            self.name, self.inner = name, real_lock(name)

        def acquire(self, wait: bool = True) -> bool:
            got = self.inner.acquire(wait=wait)
            events.append(f"+{self.name}" if got else f"!{self.name}")
            return got

        def release(self) -> None:
            events.append(f"-{self.name}")
            self.inner.release()

    monkeypatch.setattr(backend, "lock", Spy)
    real_publish = frame_and_publish

    def publish(run: Any, parts: Any) -> None:
        events.append("publish")
        real_publish(run, parts)

    real_compute = outcomes.compute_batch

    def compute(*a: Any, **k: Any) -> Any:
        events.append(f"compute:{'ingest' if '+ingest' in events[-1:] else 'free'}")
        assert not any(r.status == RunStatus.RUNNING for r in world.writer.runs_for(outcomes.TASK))
        return real_compute(*a, **k)

    monkeypatch.setattr(outcomes, "frame_and_publish", publish)
    monkeypatch.setattr(outcomes, "compute_batch", compute)
    record = world.run(batch=2)
    assert record.status == RunStatus.COMPLETE and record.stats["batches"] == 3  # 5 ends, 2 each
    ingest = [e for e in events if e.endswith("ingest") or e == "publish"]
    # +ingest publish -ingest, three times: one publish per hold, never two
    assert ingest == ["+ingest", "publish", "-ingest"] * 3
    assert events.count("+ingest-tree") == 6  # compute, then publish, per batch
    assert all(e == "compute:free" for e in events if e.startswith("compute"))


def test_nothing_starts_or_publishes_inside_the_nightly_window() -> None:
    nightly = NightlySettings()
    wed = date(2026, 11, 4)
    inside = datetime(2026, 11, 4, 22, 30, tzinfo=UTC)  # 14:30 pacific, the close is 13:00
    assert nightly_window(inside, nightly) is not None
    assert nightly_window(datetime(2026, 11, 4, 20, tzinfo=UTC), nightly) is None  # 12:00 pacific
    assert nightly_window(datetime(2026, 11, 5, 8, tzinfo=UTC), nightly) is None  # past 23:00
    assert nightly_window(datetime(2026, 11, 7, 22, tzinfo=UTC), nightly) is None  # Saturday
    assert wed.weekday() == 2
    world = World()
    world.now = inside
    record = world.run()
    assert record.status == RunStatus.COMPLETE
    assert world.sleeps and record.stats["waited_for_nightly"] >= 1
    started = [r.started_at for r in world.writer.runs_for(outcomes.TASK)]
    assert all(nightly_window(s, nightly) is None for s in started)


def test_a_rule_over_a_field_with_no_rows_fails_the_run_and_writes_nothing_for_it() -> None:
    when = {"all": [{"field": PERSONAL, "op": "gt", "value": 0.5}]}
    world = World(_configs(exit={"when": when}))
    record = world.run()
    assert record.status == RunStatus.FAILED
    (wanted,) = positions_wanted(load_edges(world.configs), load_templates(world.configs))
    assert "no stored partition" in record.stats["refused"][wanted.key]
    assert world.rows().empty  # not run as a rule that never fires


def test_a_gap_in_the_main_store_fails_the_run_before_a_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(outcomes, "coverage_problems", lambda *a: ["bars/1d: holds 2020-01-02"])
    world = World()
    record = world.run()
    assert record.status == RunStatus.FAILED and record.stats["coverage"]
    assert world.rows().empty


def test_coverage_names_a_table_that_starts_late_and_a_missing_session() -> None:
    class Reader:
        def __init__(self, held: dict[str, list[date]]):
            self.held = held

        def dates(self, table: str) -> list[date]:
            return self.held.get(table, [])

    full = sessions_ending(END, 5)
    held = {
        "bars/1d": [*full[:2], *full[3:]], "rates/treasury": full,
        "outcomes/instrument/forward_returns@v2": full[2:], "events/dividend": full,
    }  # fmt: skip
    problems = coverage_problems(Reader(held), full[0], full[-1])  # type: ignore[arg-type]
    assert any("bars/1d: 1 sessions missing" in p for p in problems)
    assert any("forward_returns@v2: holds" in p for p in problems)
    assert len(problems) == 2


def test_a_rerun_skips_what_is_written_and_force_rewrites_it() -> None:
    world = World()
    first = world.run()
    again = world.run()
    assert again.stats["skipped"] == first.stats["window_ends"] and again.stats["batches"] == 0
    forced = world.run(force=True)
    assert forced.stats["batches"] == 1 and forced.stats["skipped"] == 0
    batch = [r for r in world.writer.runs_for(outcomes.TASK) if r.stats.get("history_runs")][-1]
    assert set(batch.stats["history_runs"]) >= {d.isoformat() for d in DAYS[2:]}  # ADR 0084 d3


def test_a_re_imported_session_of_a_window_makes_its_end_a_new_one() -> None:
    world = World()
    first = world.run()
    write_history(
        world.history,
        [DAYS[2]],
        NAMES,
        EXPIRY,
        strikes=STRIKES,
        clock=lambda d: NOW - timedelta(days=1),
    )
    again = world.run()
    assert again.stats["skipped"] == first.stats["window_ends"] - 3  # the ends that read DAYS[2]
    assert again.stats["batches"] == 1


def test_a_busy_ingest_lock_frees_the_tree_lock_while_the_batch_waits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    backend = world.writer.backend
    busy = backend.lock("ingest")
    assert busy.acquire(wait=False)
    seen: list[bool] = []
    pacing = world.pacing()
    inner = pacing.sleep

    def sleep(seconds: float) -> None:
        free = backend.lock("ingest-tree")
        seen.append(free.acquire(wait=False))  # nothing holds the tree lock while we wait
        if seen[-1]:
            free.release()
        busy.release()  # the other writer finishes
        inner(seconds)

    pacing.sleep = sleep
    opts = HistoryOutcomeOptions(start=DAYS[2], end=END)
    record = compute_history_outcomes(
        world.ctx(), END, opts, open_store=lambda url: world.history, pacing=pacing
    )
    assert record.status == RunStatus.COMPLETE and seen and all(seen)


def test_a_field_stored_for_part_of_the_range_refuses_the_windows_it_does_not_cover() -> None:
    when = {"all": [{"field": PERSONAL, "op": "gt", "value": 0.5}]}
    world = World(_configs(exit={"when": when}))
    rows: list[dict[str, object]] = [
        {"instrument_id": n, "iv30_ibkr": 0.1} for n in ("EQ:SPY", "IDX:SPX")
    ]
    known = datetime.combine(END, datetime.min.time(), UTC) + timedelta(days=2)
    world.writer.write_table(PERSONAL_TABLE, END, "f", stamped(rows, END, "f", known))
    record = world.run()
    assert record.status == RunStatus.FAILED and record.stats["refused_windows"] > 0
    assert set(pd.to_datetime(world.rows()["window_end"]).dt.date) == {END}  # only where it reads


def test_a_window_with_a_close_the_history_lacks_is_not_written() -> None:
    days = [d for d in DAYS if d != DAYS[4]]
    world = World(days=days)
    record = world.run()
    assert record.status == RunStatus.COMPLETE, record.stats
    written = set(pd.to_datetime(world.rows()["window_end"]).dt.date)
    assert DAYS[4] not in written and DAYS[5] not in written  # both windows read the gap
