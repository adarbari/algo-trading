from datetime import date, timedelta
from typing import Any

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens import results, runs
from algotrade.services.read.screens.runs import (
    NOT_PICKED,
    DecisionCount,
    is_picked,
    latest_run,
    load_latest_runs,
    load_previous_run,
    picked_mask,
    run_rows,
)
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.read.screens.conftest import D0, D1, T, context, write_gated


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
    assert run is not None and run.audit == {}  # the record holds no stats
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
    real = results.partition

    def counting(c: ReadContext, table: str, *args: Any) -> Any:
        read.append(table)
        return real(c, table, *args)

    monkeypatch.setattr(results, "partition", counting)
    ids, total = runs.load_pick_ids(ctx, run, 100)
    assert read == []  # no results/rule_screen_values read
    rows = runs.run_rows(ctx, run)
    mine = [
        str(i)
        for i, d in zip(rows["instrument_id"], rows["decision"], strict=True)
        if runs.is_picked(str(d)) or d == runs.PAUSED
    ]
    assert ids == mine and total == len(mine) and total > 0
    assert runs.load_pick_ids(ctx, run, 1) == (mine[:1], total)
