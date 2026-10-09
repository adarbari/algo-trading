"""One night of the paper record: signals are stored when made, settled from the stored outcomes
by the edge's own hit (never a loss for a missing result), the night is idempotent and atomic,
and a read as of an earlier night shows the book as it was."""

import contextlib
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.core.time.calendar import next_session
from algotrade.data.paper import read_paper
from algotrade.services.evaluation.forward.results import job_name, paper_users, run_night
from algotrade.storage.tables.schemas import EDGE_PAPER
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    build_world,
    outcome_row,
)
from tests.unit.services.evaluation.forward.conftest import NOW, USER, Desk, desk

BUY = next_session(DAYS[0])  # the first signal's entry session
SELL = DAYS[3]  # two sessions after it


def night(d: Desk, day: date, now: datetime = NOW):  # type: ignore[no-untyped-def]
    return run_night(d.world.reader, d.world.results, d.configs, USER, day, now)


def book(d: Desk, until: date = DAYS[-1], as_of: datetime | None = None) -> pd.DataFrame:
    return read_paper(d.world.reader, "u1", DAYS[0], until, as_of)


def test_a_night_stores_the_signals_open_with_buy_and_sell_sessions(following: Desk) -> None:
    result, record = night(following, DAYS[0])
    assert result.signalled == {"drift": 5} and result.settled == {} and result.rows == 5
    rows = book(following)
    assert set(rows["status"]) == {"open"} and len(rows) == 5
    assert set(rows["buy_session"]) == {BUY} and set(rows["sell_session"]) == {SELL}
    assert rows["excess_return"].isna().all()
    assert record.job == job_name("u1") and record.stats["signalled"] == {"drift": 5}


def test_a_settled_trade_wins_by_the_edges_own_hit_from_the_stored_outcome(following: Desk) -> None:
    night(following, DAYS[0])
    result, _ = night(following, SELL)
    assert result.settled == {"drift": 5}
    first = book(following).query("signal_session == @DAYS[0]")
    assert set(first["status"]) == {"won"}
    top = first.set_index("instrument_id").loc["EQ:N19"]
    assert top["excess_return"] == 0.095 and top["rank"] == 1 and not top["delisted"]


def test_a_name_that_lost_is_lost_and_a_missing_result_is_never_a_loss() -> None:
    def rows(day: date) -> list[dict]:  # type: ignore[type-arg]
        out = [outcome_row(iid, i, day) for i, iid in enumerate(IDS) if iid != "EQ:N18"]
        out[-1] = outcome_row(IDS[19], 19, day, fwd_excess_return=-0.02)  # N19 lost
        out[-2] = outcome_row(IDS[17], 17, day, fwd_excess_return=float("nan"))  # no benchmark
        return out

    d = desk(build_world(rows_of=rows))
    night(d, DAYS[0])
    night(d, SELL)
    status = book(d).query("signal_session == @DAYS[0]").set_index("instrument_id")
    assert status.loc["EQ:N19", "status"] == "lost"
    assert (
        status.loc["EQ:N18", "status"] == "skipped"
        and "entry bar" in status.loc["EQ:N18", "reason"]
    )
    assert status.loc["EQ:N17", "status"] == "skipped"
    assert (
        status.loc["EQ:N17", "reason"] == "the result could not be computed (no benchmark return)"
    )
    assert pd.isna(status.loc["EQ:N17", "excess_return"])
    assert set(status.loc[["EQ:N16", "EQ:N15"], "status"]) == {"won"}


def test_a_window_with_no_outcome_stays_open_then_is_skipped_with_the_reason() -> None:
    d = desk(build_world(closed=[x for x in DAYS if x != BUY]))
    night(d, DAYS[0])
    night(d, SELL)
    assert set(book(d).query("signal_session == @DAYS[0]")["status"]) == {"open"}
    late = SELL + timedelta(days=14)
    d2 = desk(build_world(closed=[x for x in DAYS if x != BUY]))
    night(d2, DAYS[0])
    night(d2, late)
    skipped = book(d2, until=late).query("signal_session == @DAYS[0]")
    assert set(skipped["status"]) == {"skipped"}
    assert set(skipped["reason"]) == {"no outcome stored for its window"}


def test_an_outcome_known_after_now_does_not_settle_the_trade(following: Desk) -> None:
    night(following, DAYS[0])
    early = datetime(2026, 9, 5, tzinfo=UTC)  # the outcomes were known on 2026-09-30
    night(following, SELL, early)
    assert set(book(following).query("signal_session == @DAYS[0]")["status"]) == {"open"}


def test_a_rerun_of_a_night_adds_and_changes_nothing(following: Desk) -> None:
    night(following, DAYS[0])
    before = book(following)
    again, _ = night(following, DAYS[0])
    assert again.signalled == {} and again.rows == 0
    pd.testing.assert_frame_equal(book(following), before)
    night(following, SELL)
    settled = book(following)
    night(following, SELL)
    pd.testing.assert_frame_equal(book(following), settled)


def test_a_read_as_of_an_earlier_night_shows_the_book_as_it_was(following: Desk) -> None:
    first = datetime(2026, 10, 5, 22, tzinfo=UTC)
    night(following, DAYS[0], first)
    night(following, SELL, first + timedelta(days=1))
    assert set(
        book(following, as_of=first + timedelta(hours=1)).query("signal_session == @DAYS[0]")[
            "status"
        ]
    ) == {"open"}
    assert set(book(following).query("signal_session == @DAYS[0]")["status"]) == {"won"}


def test_a_trade_is_not_judged_by_an_outcome_the_user_edited_after_the_signal() -> None:
    d = desk()
    night(d, DAYS[0])
    edited = desk(d.world, outcome={
        "kind": "excess_return", "horizon_sessions": [2], "benchmark": "SPY",
        "start_offset_sessions": 1, "cost_bps": 5.0,
    })  # fmt: skip
    run_night(d.world.reader, d.world.results, edited.configs, USER, SELL, NOW)
    status = read_paper(d.world.reader, "u1", DAYS[0], DAYS[-1])
    rows = status[status["signal_session"] == DAYS[0]]
    assert set(rows["status"]) == {"skipped"}
    assert set(rows["reason"]) == {"the edge's outcome changed after the signal"}


def test_the_night_publishes_one_run_and_a_failed_write_leaves_nothing(following: Desk) -> None:
    class BoomError(Exception): ...

    writer = following.world.results
    original = writer.write_result

    def failing(*args, **kwargs):  # type: ignore[no-untyped-def]
        original(*args, **kwargs)
        raise BoomError

    writer.write_result = failing  # type: ignore[method-assign]
    with contextlib.suppress(BoomError):
        run_night(following.world.reader, writer, following.configs, USER, DAYS[0], NOW)
    assert book(following).empty  # pending rows were aborted, never visible


def test_only_users_with_a_followed_edge_are_signalled_for() -> None:
    d = desk()
    assert paper_users(_with_users(d.configs, ["u1", "u2"])) == [USER]


def _with_users(configs, users):  # type: ignore[no-untyped-def]
    class Store:
        def __getattr__(self, name):  # type: ignore[no-untyped-def]
            return getattr(configs, name)

        def users(self) -> list[str]:
            return users

    return Store()


def test_the_schema_keys_one_row_per_trade() -> None:
    assert EDGE_PAPER.key == ("user_id", "edge_id", "signal_session", "instrument_id")
