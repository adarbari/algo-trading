"""The ``option-history-features`` task and the splice (ADR 0088 decision 11, F7): the chain groups
computed from a history session through the splice's chain tables equal the same groups computed
by the plain runner from a Cboe-shaped chain of identical rows; they are stored in the history root
(personal), not the main store; a group is committed before the one that reads its rows
(``iv_history`` over ``iv30``); the splice sends a pre-cutover read of a chain group to the history
root and a read from the cutover to the main store, logs what it read from the root, and a range
spanning the cutover is the two parts."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.data.option_history import reading
from algotrade.data.option_history.chain_frames import (
    chain_option_quotes,
    chain_status,
    chain_underlying_quotes,
)
from algotrade.data.option_history.splice import CHAIN_GROUPS
from algotrade.features.framework.declaration import FeatureGroup
from algotrade.features.framework.runner import compute_sessions, rollup_params
from algotrade.features.site import site_features
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.runs import RunRecord, RunStatus
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.framework.run import TaskContext
from algotrade_ingestion.tasks.options_history import features
from algotrade_ingestion.tasks.options_history.features import (
    HistoryChainReader,
    HistoryFeatureOptions,
    compute_history_features,
)
from tests.conftest import REPO_ROOT
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.option_history.store import write_history
from tests.helpers.rollup_store import store, write_curve

END = date(2019, 8, 16)
DAYS = sessions_ending(END, 25)
EXPIRY = date(2019, 9, 20)
NAMES = {"SPY": ("EQ:SPY", 290.0), "SPX": ("IDX:SPX", 2900.0)}
STRIKES = (270.0, 280.0, 290.0, 300.0)
NOW = datetime(2026, 11, 4, 8, tzinfo=UTC)
CONFIGS = FileConfigStore(REPO_ROOT / "config", local=False)


class World:
    def __init__(self) -> None:
        self.history = MemoryBackend()
        write_history(self.history, DAYS, NAMES, EXPIRY, strikes=STRIKES)
        self.writer, self.reader = store()
        for day in DAYS:
            write_curve(self.writer, day, 0.02)

    def ctx(self) -> TaskContext:
        return task_ctx(self.writer, clock=lambda: NOW)

    def run(self, force: bool = False) -> RunRecord:
        opts = HistoryFeatureOptions(start=DAYS[0], end=END, force=force)
        return compute_history_features(self.ctx(), END, opts, open_store=lambda url: self.history)


def _group(key: str) -> tuple[FeatureGroup, Any]:
    groups = site_features(CONFIGS).groups
    return groups[key], rollup_params(CONFIGS, list(groups.values()))[key]


def test_a_history_day_computes_what_a_cboe_shaped_day_of_the_same_rows_computes() -> None:
    world = World()
    day = DAYS[-1]
    history = StoreReader(world.history)
    quotes = reading.option_quotes(history, day)
    assert quotes is not None
    cboe, cboe_reader = store()  # the same rows, stored as the Cboe pull stores a chain
    write_curve(cboe, day, 0.02)
    unders = reading.underlying_quotes(history, day)
    for table, frame in (
        ("chains/option_quotes", chain_option_quotes(quotes)),
        ("chains/underlying_quotes", chain_underlying_quotes(unders, quotes)),
        ("chains/status", chain_status(quotes)),
    ):
        cboe.write_table(table, day, f"c-{table}", frame)
    spliced = HistoryChainReader(world.writer.backend, history)
    for key in ("iv30@v1", "nearest_expiry@v1", "put_wing@v1", "option_liquidity@v1"):
        group, params = _group(key)
        (plain,) = list(compute_sessions(cboe_reader, group, [day], params))
        (via,) = list(compute_sessions(spliced, group, [day], params))
        assert plain.frame is not None and via.frame is not None, key
        pd.testing.assert_frame_equal(
            plain.frame.sort_values("instrument_id").reset_index(drop=True),
            via.frame.sort_values("instrument_id").reset_index(drop=True),
        )
    assert plain.frame is not None and len(plain.frame) == 2
    assert spliced.licence == "personal"


def test_the_task_stores_every_chain_group_in_the_history_root_not_the_main_store() -> None:
    world = World()
    record = world.run()
    assert record.status == RunStatus.COMPLETE, record.stats
    assert set(CHAIN_GROUPS) <= set(record.stats)
    hist = StoreReader(world.history)
    for key in ("iv30@v1", "iv_history@v2", "nearest_expiry@v1", "put_wing@v1", "skew@v1"):
        group, _ = _group(key)
        assert hist.dates(group.table) == DAYS, key
        assert world.reader.dates(group.table) == [], key  # nothing in the main store
    iv30 = hist.table("rollups/instrument/iv30@v1", DAYS[-1])
    assert iv30 is not None and set(iv30["instrument_id"]) == {"EQ:SPY", "IDX:SPX"}
    spy = iv30[iv30["instrument_id"] == "EQ:SPY"]["iv30"].iloc[0]
    assert 0.28 < spy < 0.32  # priced at 30 % vol (the test strikes sit around SPY only)
    hv = hist.table("rollups/instrument/iv_history@v2", DAYS[-1])
    assert hv is not None  # read the iv30 rows of the history root through the splice


def test_a_rerun_skips_stored_sessions_and_force_recomputes_them() -> None:
    world = World()
    world.run()
    again = world.run()
    assert again.stats["iv30@v1"]["sessions"] == 0 and again.stats["iv30@v1"]["skipped"] == len(
        DAYS
    )
    assert world.run(force=True).stats["iv30@v1"]["sessions"] == len(DAYS)


def test_the_task_needs_a_range_with_history_before_the_cutover() -> None:
    world = World()
    with pytest.raises(Exception, match="no history session"):
        compute_history_features(
            world.ctx(),
            END,
            HistoryFeatureOptions(start=FIRST_CBOE_CHAIN_SESSION, end=FIRST_CBOE_CHAIN_SESSION),
            open_store=lambda url: world.history,
        )
    assert features.CHAIN_TABLES and CHAIN_GROUPS[0] == "iv30@v1"


def test_a_re_imported_session_recomputes_its_features() -> None:
    world = World()
    world.run()
    write_history(
        world.history,
        [DAYS[3]],
        NAMES,
        EXPIRY,
        strikes=STRIKES,
        clock=lambda d: NOW - timedelta(days=1),
    )
    again = world.run()
    assert again.stats["iv30@v1"]["sessions"] == 1
    assert again.stats["iv30@v1"]["skipped"] == len(DAYS) - 1
    assert again.stats["no_id_rows"] == 0


def test_batches_commit_apart_and_a_failed_group_keeps_the_ones_before_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = World()
    real = compute_sessions

    def failing(reader: Any, group: FeatureGroup, *a: Any, **k: Any) -> Any:
        if group.key == "skew@v1":
            raise RuntimeError("boom")
        return real(reader, group, *a, **k)

    monkeypatch.setattr(features, "compute_sessions", failing)
    opts = HistoryFeatureOptions(start=DAYS[0], end=END, batch=10)
    with pytest.raises(RuntimeError, match="boom"):
        compute_history_features(world.ctx(), END, opts, open_store=lambda url: world.history)
    hist = StoreReader(world.history)
    assert hist.dates("rollups/instrument/iv30@v1") == DAYS  # three committed batches
    assert hist.dates("rollups/instrument/skew@v1") == []
    runs = StoreWriter(world.history).runs_for("option-history-features:iv30@v1")
    assert len(runs) == 3
    assert all(r.status == RunStatus.COMPLETE for r in runs)
