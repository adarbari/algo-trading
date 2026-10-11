"""One night of the paper record: signals are stored when made, settled from the stored outcomes
by the edge's own hit (never a loss for a missing result), the night is idempotent and atomic,
and a read as of an earlier night shows the book as it was."""

import contextlib
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from algotrade.config.edges.loading import load_edges
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.time.calendar import next_session
from algotrade.data.paper import job_name, read_paper, read_stored
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.forward.results import MISSED, paper_owners, run_night
from algotrade.services.evaluation.forward.settle import outcome_hash
from algotrade.services.evaluation.forward.signals import advance
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.edge_schemas import EDGE_PAPER
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import (
    DAYS,
    IDS,
    build_world,
    edge_document,
    outcome_row,
)
from tests.unit.services.evaluation.cross_section.test_harness import (
    EVENTS,
    OTM_OUTCOME,
    otm_world,
)
from tests.unit.services.evaluation.forward.conftest import (
    NOW,
    USER,
    Desk,
    desk,
    event_changes,
    event_world,
    site_desk,
)

BUY = next_session(DAYS[0])  # the first signal's entry session
SELL = DAYS[3]  # two sessions after it


def night(d: Desk, day: date, now: datetime = NOW):  # type: ignore[no-untyped-def]
    return run_night(d.world.reader, d.world.results, d.configs, USER, day, now)


def book(d: Desk, until: date = DAYS[-1], as_of: datetime | None = None) -> pd.DataFrame:
    return read_stored(d.world.reader, "u1", DAYS[0], until, as_of)


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
    status = read_stored(d.world.reader, "u1", DAYS[0], DAYS[-1])
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


def test_the_nightly_works_for_the_site_and_users_with_a_recording_edge_or_open_trades(
    following: Desk,
) -> None:
    docs = {**following.configs._docs, ("u2", "edges", "beta"): {"follow": {"since": "2026-09-01"}}}
    docs[("site", "edges", "beta")] = {
        **edge_document(id="beta", status="evidenced"),
        "evidence": {"run_id": "r1", "split_from": "2026-01-02"},
    }  # a site edge u2 follows, beside u1's own live edge
    store = _with_users(MemoryConfigStore(docs), ["u1", "u2", "u3"])
    reader = following.world.reader
    assert paper_owners(reader, store, DAYS[0]) == [UserContext(SITE_USER), USER]
    # u3 owns nothing recording but still has an open trade: it settles
    following.world.writer.write_table(
        "results/edge_paper",
        DAYS[0],
        "p3",
        stamped([trade_row("u3")], DAYS[0], "p3", NOW, "edge-signals"),
    )
    assert paper_owners(reader, store, DAYS[0]) == [
        UserContext(SITE_USER), USER, UserContext("u3")
    ]  # fmt: skip


def trade_row(user: str) -> dict:  # type: ignore[type-arg]
    return {
        "user_id": user, "edge_id": "gone", "signal_session": DAYS[0], "instrument_id": "EQ:A",
        "status": "open", "buy_session": BUY, "sell_session": SELL, "horizon_sessions": 2,
        "rank": 1, "delisted": False,
    }  # fmt: skip


def _with_users(configs, users):  # type: ignore[no-untyped-def]
    class Store:
        def __getattr__(self, name):  # type: ignore[no-untyped-def]
            return getattr(configs, name)

        def users(self) -> list[str]:
            return users

    return Store()


def test_the_run_record_says_what_each_followed_edge_did_tonight(following: Desk) -> None:
    due_night, record = night(following, DAYS[0])
    assert record.stats["tonight"] == {"drift": {"state": "signalled", "reason": ""}}
    _, off = night(following, DAYS[1])  # not due: the schedule is every second session
    assert off.stats["tonight"]["drift"]["state"] == "not_due"
    broken = desk(build_world(no_features=[DAYS[2]]))
    _, failed = night(broken, DAYS[2])  # due, but the screen could not read its features
    state = failed.stats["tonight"]["drift"]
    assert state["state"] == "skipped" and state["reason"]
    assert failed.stats["skipped"][0]["reason"] == state["reason"]
    assert due_night.signalled == {"drift": 5}


def test_a_due_edge_whose_screen_qualifies_nothing_says_no_picks() -> None:
    empty = desk(build_world(price_of=lambda day, i: -1.0))  # the rule needs price > 0
    _, record = night(empty, DAYS[0])
    assert record.stats["tonight"]["drift"] == {"state": "no_picks", "reason": ""}


def test_a_due_session_the_nightly_skipped_is_recorded_as_missed(following: Desk) -> None:
    night(following, DAYS[0])
    _, later = night(following, DAYS[4])  # DAYS[2] was due and nobody ran it
    assert later.stats["missed"] == [
        {"edge": "drift", "session": DAYS[2].isoformat(), "reason": MISSED}
    ]
    _, adjacent = night(following, DAYS[2])
    assert adjacent.stats["missed"] == []


def test_the_schema_keys_one_row_per_trade() -> None:
    assert EDGE_PAPER.key == ("user_id", "edge_id", "signal_session", "instrument_id")


# ---- the paper record of a historical session equals the harness's legs for it ---------------


def paper_over_days(d: Desk) -> pd.DataFrame:
    """Every session of the world's days as a night, so the trades signalled settle."""
    for day in [*DAYS, advance(DAYS[-1], 4)]:  # the last night settles the last windows
        night(d, day)
    return book(d, until=advance(DAYS[-1], 4))


def assert_equals_the_harness(d: Desk) -> pd.DataFrame:
    """Per block of the harness's legs: the counted picks and the hits of the paper trades signalled
    in it are the harness's ``pick_values`` and ``pick_hits``."""
    (edge,) = load_edges(d.configs, "u1")
    (variant,) = evaluate_edge(
        d.world.reader, d.world.results, d.configs, USER, edge, DAYS[0], DAYS[-1], NOW
    ).results
    paper = paper_over_days(d)
    counted = paper[paper["status"].isin(["won", "lost"])]
    horizon = edge.outcome.horizon_sessions[0]
    stats = variant.stats
    for stat, following in zip(stats, [*[s.session for s in stats[1:]], None], strict=True):
        mine = counted[
            (counted["signal_session"] >= stat.session)
            & (following is None or counted["signal_session"] < following)
        ]
        assert len(mine) == len(stat.pick_values)
        assert int((mine["status"] == "won").sum()) == stat.pick_hits
    assert (paper["horizon_sessions"] == horizon).all()
    return paper


def test_the_event_paper_trades_equal_the_harness_legs() -> None:
    d = desk(event_world(EVENTS), **event_changes(2))
    paper = assert_equals_the_harness(d)
    assert sorted(set(paper["signal_session"])) == [DAYS[1], DAYS[2], DAYS[5]]
    assert (paper["buy_session"] == paper["signal_session"].map(next_session)).all()
    assert len(paper) == 8 and set(paper["status"]) == {"won", "lost"}


def test_the_vrp_paper_trades_settle_by_the_harnesss_expires_otm_rule() -> None:
    d = desk(otm_world(), outcome=OTM_OUTCOME)
    paper = assert_equals_the_harness(d)
    settled = paper[paper["signal_session"] == DAYS[0]]
    assert set(settled["status"]) == {"won"} and settled["excess_return"].isna().all()


def test_a_vrp_trade_the_window_breached_is_lost() -> None:
    poisoned = otm_world({BUY})
    d = desk(poisoned, outcome=OTM_OUTCOME)
    paper = assert_equals_the_harness(d)
    first = paper[paper["signal_session"] == DAYS[0]]
    assert set(first["status"]) == {"lost"}


def test_a_vrp_trade_with_no_usable_implied_vol_is_skipped_never_lost() -> None:
    w = build_world()
    levels = {DAYS[0]: 50.0, DAYS[2]: None}  # garbage on one decision session, no vol on another
    for day in [*DAYS, next_session(DAYS[-1])]:
        level = levels.get(day, 0.4)
        iv = [
            {"instrument_id": i, "iv30_ibkr": float("nan") if level is None else level} for i in IDS
        ]
        w.writer.write_table(
            "rollups/instrument/ibkr_iv@v1", day, f"ib-{day}", stamped(iv, day, f"ib-{day}")
        )
    paper = paper_over_days(desk(w, outcome=OTM_OUTCOME))
    garbage = paper[paper["signal_session"] == DAYS[0]]
    assert set(garbage["status"]) == {"skipped"} and set(garbage["reason"]) == {
        "the implied vol stored at the signal session was not usable"
    }
    missing = paper[paper["signal_session"] == DAYS[2]]
    assert set(missing["status"]) == {"skipped"} and set(missing["reason"]) == {
        "no implied vol was stored for the name at the signal session"
    }
    assert set(paper[paper["signal_session"] == DAYS[4]]["status"]) == {"won"}


def test_an_event_night_is_idempotent() -> None:
    d = desk(event_world(EVENTS), **event_changes(2))
    first = night(d, DAYS[1])[0]
    before = book(d)
    again = night(d, DAYS[1])[0]
    assert first.signalled == {"drift": 3} and again.signalled == {} and again.rows == 0
    pd.testing.assert_frame_equal(book(d), before)


# ---- paper trades follow the edge's owner, never a follower (ADR 0053 amendment 2026-10-10) ----


SITE = UserContext(SITE_USER)


def site_night(d: Desk, day: date, user: UserContext = SITE, now: datetime = NOW):  # type: ignore[no-untyped-def]
    return run_night(d.world.reader, d.world.results, d.configs, user, day, now)


def shared(d: Desk, until: date = DAYS[-1]) -> pd.DataFrame:
    """What every follower of the site's ``drift`` reads: the site's record of it."""
    return read_paper(d.world.reader, {"drift": SITE_USER}, DAYS[0], until)


def test_a_follower_of_a_site_edge_gets_no_trades_from_the_nightly() -> None:
    d = site_desk()
    for follower in ("u1", "u2"):
        result, record = site_night(d, DAYS[0], UserContext(follower))
        assert result.signalled == {} and result.rows == 0 and result.tonight == {}
        assert record.job == job_name(follower)
    assert read_stored(d.world.reader, "u1", DAYS[0], DAYS[-1]).empty
    assert shared(d).empty  # nothing duplicated, nothing recorded until the site's own night
    result, _ = site_night(d, DAYS[0])
    assert result.signalled == {"drift": 5}
    assert set(shared(d)["user_id"]) == {SITE_USER} and len(shared(d)) == 5


def test_a_site_edge_records_while_evidenced_or_live_and_a_retired_one_only_settles() -> None:
    for status, rows in (("candidate", 0), ("researching", 0), ("rejected", 0), ("evidenced", 5),
                         ("live", 5)):  # fmt: skip
        d = site_desk(status=status, followers=())
        result, record = site_night(d, DAYS[0])
        assert (result.rows, record.stats["tonight"] != {}) == (rows, bool(rows)), status
    d = site_desk(followers=())
    site_night(d, DAYS[0])
    retired = site_desk(d.world, followers=(), status="retired")
    result, _ = site_night(retired, SELL)  # DAYS[2] was due, but a retired edge takes no pick
    assert result.settled == {"drift": 5} and result.signalled == {} and result.rows == 5
    assert set(shared(retired)["status"]) == {"won"} and len(shared(retired)) == 5


def test_a_record_starts_the_first_night_the_job_sees_the_status_and_is_never_backfilled() -> None:
    d = site_desk(followers=())
    _, first = site_night(d, DAYS[3])  # the edge was evidenced long before: nothing before this
    assert first.stats["tonight"]["drift"]["state"] == "signalled" and first.stats["missed"] == []
    assert set(shared(d)["signal_session"]) == {DAYS[3]}
    _, later = site_night(d, DAYS[5])  # DAYS[3] + one horizon is due and was run
    assert set(shared(d)["signal_session"]) == {DAYS[3], DAYS[5]}
    assert later.stats["missed"] == []
    _, gap = site_night(d, advance(DAYS[5], 5))  # a gap after the record began is filled
    assert [m["session"] for m in gap.stats["missed"]] == [
        advance(DAYS[3], 2 * k).isoformat() for k in (2, 3)
    ]


def test_a_followers_own_universe_and_screen_do_not_change_the_site_record() -> None:
    plain = site_desk(followers=())
    site_night(plain, DAYS[0])
    own = site_desk(followers=("u1",))
    docs = dict(own.configs._docs)
    docs[("u1", "selections", "active")] = {"id": "active", "where": {"price": {"lt": 1}}}
    docs[("u1", "strategies", "momo")] = docs[("site", "strategies", "momo")]
    mine = Desk(own.world, MemoryConfigStore(docs))
    site_night(mine, DAYS[0])
    pd.testing.assert_frame_equal(
        shared(mine).drop(columns=["knowledge_ts", "config_hash"]),
        shared(plain).drop(columns=["knowledge_ts", "config_hash"]),
    )


def test_a_followers_old_rows_settle_but_stay_out_of_the_shared_record() -> None:
    d = site_desk(followers=("u1",))
    (edge,) = [e for e in load_edges(d.configs, "u1") if e.id == "drift"]
    old = [
        {**trade_row("u1"), "edge_id": "drift", "instrument_id": f"EQ:N{i:02d}",
         "outcome_hash": outcome_hash(edge), "screener": "momo", "rank": r, "config_hash": "x"}
        for r, i in enumerate((19, 18, 17, 16, 15), start=1)
    ]  # fmt: skip
    d.world.writer.write_table(
        "results/edge_paper",
        DAYS[0],
        "p1",
        stamped(old, DAYS[0], "p1", NOW - timedelta(days=1), "edge-signals"),
    )
    reader = d.world.reader
    site_owner = UserContext(SITE_USER)  # the site edge itself is evidenced: it records
    assert paper_owners(reader, d.configs, SELL) == [site_owner, UserContext("u1")]  # u1: open
    result, _ = site_night(d, SELL, UserContext("u1"))
    assert result.settled == {"drift": 5} and result.signalled == {}
    assert set(read_stored(reader, "u1", DAYS[0], DAYS[-1])["status"]) == {"won"}
    assert shared(d).empty  # the shared record is the site's own rows only
    assert paper_owners(reader, d.configs, SELL) == [site_owner]  # none left open: u1's job stops


def test_a_record_that_was_broken_starts_afresh_when_the_edge_records_again() -> None:
    d = site_desk(followers=())
    site_night(d, DAYS[0])  # evidenced: a record begins at DAYS[0] (due every second session)
    candidate = site_desk(d.world, followers=(), status="candidate")
    site_night(candidate, DAYS[1])  # a complete night that does not list the edge breaks the run
    _, again = site_night(d, DAYS[3])  # DAYS[0]'s cadence says not due; a fresh start is due
    assert again.stats["tonight"]["drift"]["state"] == "signalled"
