"""``trigger_periods`` (ADR 0075): the trigger sessions read one at a time from the market
entity's stored row, windows that never overlap (a trigger within the last window is skipped),
a base tiled from the range start that holds no session of any window (a skipped trigger's, an
earlier one's and a range-end-cut one's included), a missing partition an error, a stale reading
not known (its stretches left out and reported, never "no trigger"), and no lookahead."""

from datetime import UTC, date, datetime

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session, previous_session, sessions_between
from algotrade.data import StoreReader
from algotrade.features.rollups.market.edges.triggers import NONE_SEEN
from algotrade.services.evaluation.time_series import triggers
from algotrade.services.evaluation.time_series.evaluate import evaluate_time_series
from algotrade.services.evaluation.time_series.periods import Period
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.time_series.conftest import build_world, timed_edge

TABLE = "rollups/market/market_triggers@v1"
H = 5
FIRST, LAST = date(2024, 1, 2), date(2024, 12, 27)
AS_OF = datetime(2026, 10, 20, tzinfo=UTC)
STORED_FROM = date(2023, 12, 1)


def row(day: date, fired: bool, stale: bool) -> dict[str, object]:
    """A stored market row: the spike's date and 0 on its session, null for a stale reading,
    ``NONE_SEEN`` for fresh readings with no spike."""
    since = None if stale else 0 if fired else NONE_SEEN
    return {
        "instrument_id": "MKT:US",
        "vix_spike_date": day if fired else None,
        "sessions_since_vix_spike": since,
        "vix_spike_level": 35.0 if fired else None,
    }


def world(
    fired: list[date], stale: tuple[date, ...] = (), until: date = LAST, skip: tuple[date, ...] = ()
) -> StoreReader:
    """A partition for every session from ``STORED_FROM`` to ``until`` (but ``skip``)."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day in sessions_between(STORED_FROM, until):
        if day not in skip:
            r = row(day, day in fired, day in stale)
            writer.write_table(TABLE, day, f"t-{day}", stamped([r], day, f"t-{day}"))
    return reader_of(backend)


def reader_of(backend: MemoryBackend) -> StoreReader:
    return StoreReader(backend)


def run(reader: StoreReader, last: date = LAST) -> triggers.Placed:
    return triggers.trigger_periods(reader, "vix_spike", FIRST, last, H, AS_OF)


def placed(fired: list[date], last: date = LAST) -> list[Period]:
    return run(world(fired, until=last), last).periods


def sessions_of(p: Period) -> list[date]:
    out, day = [], next_session(p.entry)
    for _ in range(H):
        out.append(day)
        day = next_session(day)
    return out


def test_a_trigger_is_the_session_its_stored_row_dates_itself() -> None:
    d = date(2024, 3, 1)
    r = world([d])
    assert triggers.reading(r, "vix_spike", d, AS_OF) == (True, True)
    assert triggers.reading(r, "vix_spike", next_session(d), AS_OF) == (False, True)  # none seen


def test_a_stale_reading_is_not_known_and_a_missing_partition_is_none() -> None:
    d = date(2024, 3, 1)
    r = world([], stale=(d,), skip=(next_session(d),))
    assert triggers.reading(r, "vix_spike", d, AS_OF) == (False, False)
    assert triggers.reading(r, "vix_spike", next_session(d), AS_OF) is None


def test_a_missing_partition_in_the_range_is_an_error_before_it_is_not() -> None:
    inside = date(2024, 5, 1)
    with pytest.raises(ConfigurationError, match="no stored market row"):
        run(world([], skip=(inside,)))
    before = previous_session(FIRST)
    assert run(world([], skip=(before,))).periods  # before the range: nothing to place


def test_the_window_follows_the_decision_session_and_covers_the_horizon() -> None:
    d = date(2024, 3, 1)
    (window,) = [p for p in placed([d]) if p.inside]
    assert (window.decision, window.entry) == (d, next_session(d))
    assert window.first == next_session(window.entry)
    assert len(sessions_of(window)) == H


def test_windows_never_overlap_a_trigger_within_the_last_window_is_skipped() -> None:
    first = date(2024, 3, 1)
    inside = next_session(next_session(first))
    after = next_session(sessions_of(next(p for p in placed([first]) if p.inside))[-1])
    counted = [p for p in placed([first, inside, after]) if p.inside]
    assert [p.decision for p in counted] == [first, after]  # `inside` is skipped
    assert sessions_of(counted[0])[-1] < counted[1].first  # disjoint, in order


def test_the_base_holds_no_session_of_any_window() -> None:
    fired = [date(2024, 3, 1), date(2024, 3, 5), date(2024, 6, 3), date(2024, 12, 24)]
    got = placed(fired)
    wins = [s for p in got if p.inside for s in sessions_of(p)]
    skipped = triggers._window(date(2024, 3, 5), H)
    cut = triggers._window(date(2024, 12, 24), H)  # runs past LAST
    stretches = [p for p in got if not p.inside]
    assert stretches
    for p in stretches:
        held = sessions_of(p)
        assert len(held) == H and held[-1] <= LAST
        assert not set(held) & {*wins, *skipped, *cut}
    assert all(not set(sessions_of(a)) & set(sessions_of(b))
               for a in stretches for b in stretches if a is not b)  # fmt: skip


def test_a_range_with_no_trigger_still_has_a_base_from_its_first_session() -> None:
    got = placed([])
    assert not [p for p in got if p.inside]
    stretches = [p for p in got if not p.inside]
    assert stretches and sessions_of(stretches[0])[0] == FIRST  # tiled from `first`
    assert sessions_of(stretches[-1])[-1] <= LAST


def test_sessions_before_the_first_trigger_are_in_the_base() -> None:
    got = placed([date(2024, 6, 3)])
    assert sessions_of(next(p for p in got if not p.inside))[0] == FIRST


def test_a_trigger_just_before_the_range_occupies_its_first_sessions() -> None:
    early = previous_session(FIRST)  # its window runs into the range
    stretches = [p for p in placed([early]) if not p.inside]
    taken = set(triggers._window(early, H))
    assert taken & set(sessions_between(FIRST, LAST))
    assert all(not set(sessions_of(p)) & taken for p in stretches)


def test_a_window_cut_by_the_range_end_is_not_counted() -> None:
    cut = date(2024, 12, 24)
    assert not [p for p in placed([cut]) if p.inside]
    assert triggers._window(cut, H)[-1] > LAST


def test_a_stale_session_drops_its_stretches_and_is_never_no_trigger() -> None:
    stale = date(2024, 5, 1)
    full = run(world([]))
    got = run(world([], stale=(stale,)))
    assert got.dropped >= 1
    assert len(got.periods) == len(full.periods) - got.dropped
    for p in got.periods:
        assert stale not in {*sessions_of(p), p.decision}
    assert full.dropped == 0


def test_no_lookahead_a_partition_after_the_range_changes_nothing() -> None:
    fired = [date(2024, 3, 1), date(2024, 6, 3)]
    base = run(world(fired))
    later = run(world([*fired, date(2025, 1, 6)], until=date(2025, 3, 31)))
    assert later == base


def test_refuses_an_unknown_trigger_and_a_zero_horizon() -> None:
    r = world([])
    with pytest.raises(ConfigurationError, match="unknown market trigger"):
        triggers.trigger_periods(r, "fomc", FIRST, LAST, H, AS_OF)
    with pytest.raises(ConfigurationError, match="horizon"):
        triggers.trigger_periods(r, "vix_spike", FIRST, LAST, 0, AS_OF)


def test_an_on_market_edge_is_evaluated_and_reports_the_stale_stretches_as_lost() -> None:
    w = build_world()
    fired = [date(2024, 3, 1), date(2024, 6, 3)]
    stale = (date(2024, 9, 10),)
    for d in sessions_between(STORED_FROM, LAST):
        r = row(d, d in fired, d in stale)
        w.writer.write_table(TABLE, d, f"t-{d}", stamped([r], d, f"t-{d}"))
    edge = timed_edge(
        schedule="on_market:vix_spike",
        outcome={"kind": "excess_return", "horizon_sessions": [H], "benchmark": "none",
                 "start_offset_sessions": 1},
    )  # fmt: skip
    ran = evaluate_time_series(
        w.reader, edge, FIRST, LAST, AS_OF, lambda d: "calm", None, False, 10
    )
    assert (ran.window, ran.horizon, ran.scheduled) == ("vix_spike", H, 2)
    (spy,) = ran.results
    assert spy.lost[triggers.STALE] >= 1


def test_a_trigger_on_the_session_before_a_weekend_first_is_scanned() -> None:
    saturday, friday = date(2024, 1, 6), date(2024, 1, 5)
    r = world([friday])
    got = triggers.trigger_periods(r, "vix_spike", saturday, LAST, H, AS_OF)
    taken = set(triggers._window(friday, H))
    base = [p for p in got.periods if not p.inside]
    assert base and all(not set(sessions_of(p)) & taken for p in base)
