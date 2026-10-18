"""``trigger_periods`` (ADR 0075): the trigger sessions read one at a time from the market
entity's stored row, windows that never overlap (a trigger within the last window is skipped),
a base that holds no session of any window (a skipped trigger's and a range-end-cut one's
included), and no lookahead (a partition after the range changes nothing)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session, previous_session
from algotrade.data import StoreReader
from algotrade.services.evaluation.time_series import triggers
from algotrade.services.evaluation.time_series.evaluate import evaluate_time_series
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.time_series.conftest import build_world, timed_edge

TABLE = "rollups/market/market_triggers@v1"
H = 5
FIRST, LAST = date(2024, 1, 2), date(2024, 12, 27)
AS_OF = datetime(2026, 10, 20, tzinfo=UTC)


def world(fired: dict[date, date | None]) -> tuple[StoreWriter, StoreReader]:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day, spike in fired.items():
        row = {"instrument_id": "MKT:US", "vix_spike_date": spike,
               "sessions_since_vix_spike": 0, "vix_spike_level": 35.0}  # fmt: skip
        writer.write_table(TABLE, day, f"t-{day}", stamped([row], day, f"t-{day}"))
    return writer, StoreReader(backend)


def placed(fired: list[date], last: date = LAST) -> list[triggers.Period]:
    _, reader = world({d: d for d in fired})
    return triggers.trigger_periods(reader, "vix_spike", FIRST, last, H, AS_OF)


def sessions_of(p: triggers.Period) -> list[date]:
    out, day = [], next_session(p.entry)
    for _ in range(H):
        out.append(day)
        day = next_session(day)
    return out


def test_a_trigger_is_the_session_its_stored_row_dates_itself() -> None:
    d = date(2024, 3, 1)
    _, reader = world({d: d, next_session(d): d})  # the next session's row holds the old date
    assert triggers.triggered(reader, "vix_spike", d, AS_OF)
    assert not triggers.triggered(reader, "vix_spike", next_session(d), AS_OF)
    assert not triggers.triggered(reader, "vix_spike", date(2024, 3, 8), AS_OF)  # nothing stored


def test_a_null_date_is_no_trigger() -> None:
    d = date(2024, 3, 1)
    _, reader = world({d: None})
    assert not triggers.triggered(reader, "vix_spike", d, AS_OF)


def test_the_window_follows_the_decision_session_and_covers_the_horizon() -> None:
    d = date(2024, 3, 1)
    (window,) = [p for p in placed([d]) if p.inside]
    assert (window.decision, window.entry) == (d, next_session(d))
    assert window.first == next_session(window.entry)
    assert len(sessions_of(window)) == H


def test_windows_never_overlap_a_trigger_within_the_last_window_is_skipped() -> None:
    first = date(2024, 3, 1)
    inside = next_session(next_session(first))  # S = first + 1; the window is S+1 .. S+5
    after = next_session(sessions_of(next(p for p in placed([first]) if p.inside))[-1])
    counted = [p for p in placed([first, inside, after]) if p.inside]
    assert [p.decision for p in counted] == [first, after]  # `inside` is skipped
    assert sessions_of(counted[0])[-1] < counted[1].first  # disjoint, in order


def test_the_base_holds_no_session_of_any_window() -> None:
    fired = [date(2024, 3, 1), date(2024, 3, 5), date(2024, 6, 3), date(2024, 12, 24)]
    got = placed(fired)
    wins = [s for p in got if p.inside for s in sessions_of(p)]
    skipped = [s for d in (date(2024, 3, 5),) for s in triggers._window(d, H)]
    cut = triggers._window(date(2024, 12, 24), H)  # runs past LAST
    stretches = [p for p in got if not p.inside]
    assert stretches
    for p in stretches:
        held = sessions_of(p)
        assert len(held) == H and held[-1] <= LAST
        assert not set(held) & {*wins, *skipped, *cut}
    assert all(len(set(sessions_of(a)) & set(sessions_of(b))) == 0
               for a in stretches for b in stretches if a is not b)  # fmt: skip


def test_a_window_cut_by_the_range_end_is_not_counted() -> None:
    cut = date(2024, 12, 24)
    got = placed([cut])
    assert not [p for p in got if p.inside]
    assert triggers._window(cut, H)[-1] > LAST


def test_no_lookahead_a_partition_after_the_range_changes_nothing() -> None:
    fired = {date(2024, 3, 1): date(2024, 3, 1), date(2024, 6, 3): date(2024, 6, 3)}
    _, reader = world(fired)
    base = triggers.trigger_periods(reader, "vix_spike", FIRST, LAST, H, AS_OF)
    later = {**fired, date(2025, 1, 6): date(2025, 1, 6)}
    _, reader2 = world(later)
    assert triggers.trigger_periods(reader2, "vix_spike", FIRST, LAST, H, AS_OF) == base


def test_a_trigger_before_the_range_is_not_read() -> None:
    before = previous_session(FIRST)
    assert not [p for p in placed([before]) if p.inside]


def test_refuses_an_unknown_trigger_and_a_zero_horizon() -> None:
    _, reader = world({})
    with pytest.raises(ConfigurationError, match="unknown market trigger"):
        triggers.trigger_periods(reader, "fomc", FIRST, LAST, H, AS_OF)
    with pytest.raises(ConfigurationError, match="horizon"):
        triggers.trigger_periods(reader, "vix_spike", FIRST, LAST, 0, AS_OF)


def test_a_window_is_the_horizon_sessions_after_the_entry_session() -> None:
    d = date(2024, 3, 1)
    window = triggers._window(d, 3)
    assert window[0] == next_session(next_session(d))
    assert pd.Series(window).is_monotonic_increasing


def test_an_on_market_edge_is_evaluated_over_its_trigger_windows() -> None:
    w = build_world()
    fired = [date(2024, 3, 1), date(2024, 6, 3)]
    for d in fired:
        row = {"instrument_id": "MKT:US", "vix_spike_date": d,
               "sessions_since_vix_spike": 0, "vix_spike_level": 35.0}  # fmt: skip
        w.writer.write_table(TABLE, d, f"t-{d}", stamped([row], d, f"t-{d}"))
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
    assert (
        spy.measures[0].picks + sum(spy.lost.values()) >= 2
    )  # windows measured or lost, by reason
