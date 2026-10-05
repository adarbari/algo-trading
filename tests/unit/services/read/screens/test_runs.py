from datetime import date, timedelta

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens.runs import (
    DecisionCount,
    is_picked,
    latest_run,
    load_latest_runs,
    run_rows,
)
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.screens.conftest import D0, D1, T


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
    assert found.not_run == Unknown(
        UnknownCode.NOT_RUN, "gamma (me) has no run in results/rule_screen for 2026-10-01"
    )


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
    assert found.not_run.detail == "results/rule_screen has no partition for 2026-10-02"


def test_an_earlier_session_reads_its_own_runs(reader: StoreReader) -> None:
    older = latest_run(_on(reader, D0), "me", "gamma")
    assert older.run is not None and older.run.session == D0


def test_picked_is_every_decision_but_reject_skipped_unknown() -> None:
    assert all(is_picked(d) for d in ("QUALIFIED", "WATCH", "EVENT_RISK", "LIQUIDITY_RISK"))
    assert not any(is_picked(d) for d in ("REJECT", "SKIPPED", "UNKNOWN"))
