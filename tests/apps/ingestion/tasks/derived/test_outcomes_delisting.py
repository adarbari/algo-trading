"""The delisting return of the ``outcomes`` task (ADR 0087 decision 5): ``forward_returns@v3``
beside v2 (whose rows do not move), the events read from the latest snapshot at write time
whatever their ``known_from``, applied only to a DELISTED name whose last bar is the event's last
session inside (S, T]; ``NO_EVENT`` and never a silent zero without one; a late event rewrites
the row."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.core.time.calendar import sessions_ending
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas.validation import validate_frame
from algotrade_ingestion.tasks.derived.outcome_paths import (
    Window,
    unapplied_delistings,
    v2_view,
    v3_view,
    window_rows,
)
from algotrade_ingestion.tasks.derived.outcomes import (
    TABLE,
    TABLE_V3,
    check_outcomes,
    compute_outcomes,
)
from tests.apps.ingestion.tasks.derived.test_outcomes import _outcomes, _store
from tests.apps.ingestion.tasks.derived.test_outcomes_listings import Z
from tests.apps.ingestion.tasks.derived.test_outcomes_listings import _store as _listing_store
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import END, write_rows

_LAST = sessions_ending(END, 4)[0]  # D's last bar in ``_store``
W = Window(tuple(date(2026, 10, d) for d in (5, 6, 7, 8, 9)))


def _bars(closes: dict[str, list[float | None]]) -> pd.DataFrame:
    rows = [
        {"instrument_id": i, "session_date": d, "high": c, "low": c, "close": c}
        for i, series in closes.items()
        for d, c in zip(W.sessions, series, strict=True)
        if c is not None
    ]
    return pd.DataFrame(rows)


def _event(
    day: date, value: float = -0.55, basis: str = "REPLACEMENT"
) -> dict[str, list[tuple[date, float, str]]]:
    return {"EQ:D": [(day, value, basis)]}


def _row(rows: pd.DataFrame, iid: str = "EQ:D") -> pd.Series:
    found: pd.Series = rows.set_index("instrument_id").loc[iid]
    return found


def test_the_event_on_the_last_bar_applies() -> None:
    bars = _bars({"EQ:D": [50, 45, 40, None, None], "SPY": [400, 404, 400, 408, 420]})
    rows, _ = window_rows(
        bars, W, {"EQ:D"}, "SPY", {"EQ:D": W.sessions[3]}, events=_event(W.sessions[2])
    )
    v3 = _row(v3_view(rows))
    assert (v3["delisting_basis"], v3["delisting_return"]) == ("REPLACEMENT", -0.55)
    assert v3["fwd_return"] == pytest.approx(0.8 * 0.45 - 1)  # (1 - 0.20)(1 - 0.55) - 1
    assert v3["fwd_excess_return"] == pytest.approx(v3["fwd_return"] - 0.0)
    assert v3["fwd_max_drawdown"] == pytest.approx(0.20)  # the path stops at the last bar
    assert _row(v2_view(rows))["fwd_return"] == pytest.approx(-0.20)  # v2 does not move
    assert "delisting_basis" not in v2_view(rows).columns


@pytest.mark.parametrize("day", [W.start, date(2026, 10, 8), date(2026, 10, 12)])
def test_an_event_outside_s_t_or_not_on_the_last_bar_is_not_applied(day: date) -> None:
    bars = _bars({"EQ:D": [50, 45, 40, None, None]})
    rows, _ = window_rows(bars, W, {"EQ:D"}, None, {"EQ:D": W.sessions[3]}, events=_event(day))
    d = _row(rows)
    assert d["delisting_basis"] == "NO_EVENT" and np.isnan(d["delisting_return"])
    assert _row(v3_view(rows))["fwd_return"] == pytest.approx(-0.20)  # never a silent zero step


def test_a_delisted_name_with_no_event_is_no_event_not_zero() -> None:
    bars = _bars({"EQ:D": [50, 45, None, None, None]})
    rows, _ = window_rows(bars, W, {"EQ:D"}, None, {"EQ:D": W.sessions[2]}, events={})
    assert _row(rows)["delisting_basis"] == "NO_EVENT"


def test_an_event_in_the_window_on_a_name_with_a_bar_at_t_stays_complete_and_is_counted() -> None:
    bars = _bars({"EQ:D": [50, 45, 40, 41, 42]})
    events = _event(W.sessions[2])
    rows, _ = window_rows(bars, W, {"EQ:D"}, None, {}, events=events)
    d = _row(rows)
    assert d["outcome_status"] == "COMPLETE" and d["delisting_basis"] is None
    assert _row(v3_view(rows))["fwd_return"] == pytest.approx(-0.16)
    assert unapplied_delistings(rows, W, events) == 1


def test_a_zero_step_leaves_the_return_exactly() -> None:
    bars = _bars({"EQ:D": [50, 45, 40, None, None]})
    rows, _ = window_rows(
        bars, W, {"EQ:D"}, None, {"EQ:D": W.sessions[3]},
        events=_event(W.sessions[2], 0.0, "ZERO_ACQUIRED"),
    )  # fmt: skip
    assert _row(v3_view(rows))["fwd_return"] == _row(rows)["fwd_return"]
    assert unapplied_delistings(rows, W, _event(W.sessions[2], 0.0, "ZERO_ACQUIRED")) == 0


def test_without_events_the_rows_have_no_delisting_columns() -> None:
    bars = _bars({"EQ:D": [50, 45, 40, None, None]})
    rows, _ = window_rows(bars, W, {"EQ:D"}, None, {"EQ:D": W.sessions[3]})
    assert "delisting_basis" not in rows.columns


def _events(  # type: ignore[no-untyped-def]
    writer,
    days: list[date],
    last: date,
    known: date,
    iid: str = "EQ:D",
    also: dict[str, date] | None = None,
) -> None:
    """One full snapshot: ``iid`` ended on ``last``; ``also``: more id -> last session."""
    rows = [
        {"instrument_id": i, "ts": pd.Timestamp(d, tz="UTC"), "known_from": known,
         "last_session": d, "last_close": 1.0, "reason": "BANKRUPTCY",
         "terminal_basis": "REPLACEMENT", "delisting_return": -0.55}
        for i, d in {iid: last, **(also or {})}.items()
    ]  # fmt: skip
    write_rows(writer, "events/delisting", days[-1], rows)


def _d_rows(reader: StoreReader, table: str) -> pd.DataFrame:
    """D's DELISTED rows of windows that start before its last bar (its last session is in
    (S, T]; D's last bar is the 4th session from the end, S there is a flat NO_EVENT row)."""
    frame = _outcomes(reader, table)
    frame = frame[pd.to_datetime(frame["session_date"]).dt.date < _LAST]
    gone = frame["outcome_status"] == "DELISTED"  # a window with a bar at T is COMPLETE
    return frame[(frame["instrument_id"] == "EQ:D") & (frame["benchmark"] == "SPY") & gone]


def test_v2_is_unchanged_by_the_delisting_return_and_v3_carries_it() -> None:
    plain_writer, plain_reader, days = _store(event_only=True)
    event_writer, event_reader, _ = _store(event_only=True)
    # known_from long after every window end: the label still reads it
    _events(event_writer, days, days[-4], days[-1] + timedelta(days=60),
            also={"EQ:E": days[-6]})  # only an event marks E gone  # fmt: skip
    for writer in (plain_writer, event_writer):
        record = compute_outcomes(task_ctx(writer), days[-1])
        assert record.status == RunStatus.COMPLETE, record.stats
    pd.testing.assert_frame_equal(_outcomes(plain_reader, TABLE), _outcomes(event_reader, TABLE))
    e3 = _outcomes(event_reader, TABLE_V3)
    e3 = e3[e3["instrument_id"] == "EQ:E"]
    assert "DELISTED" in set(e3["outcome_status"])  # v3 counts the event-only departure ...
    e2 = _outcomes(event_reader, TABLE)
    assert "DELISTED" not in set(e2[e2["instrument_id"] == "EQ:E"]["outcome_status"])  # v2 not
    v3 = _d_rows(event_reader, TABLE_V3)
    assert len(v3) and set(v3["delisting_basis"]) == {"REPLACEMENT"}
    v2 = _d_rows(event_reader, TABLE).set_index("horizon_sessions")["fwd_return"]
    got = v3.set_index("horizon_sessions")["fwd_return"]
    assert np.allclose((1 + v2) * 0.45 - 1, got)
    plain = _d_rows(plain_reader, TABLE_V3)
    assert set(plain["delisting_basis"]) == {"NO_EVENT"} and plain["delisting_return"].isna().all()


def test_a_backfill_reads_todays_snapshot_and_writes_v3_only() -> None:
    writer, reader, days = _store()
    _events(writer, days, days[-4], days[-1])
    compute_outcomes(task_ctx(writer), days[-1], days[-6], days[-1])
    assert not reader.dates(TABLE) and reader.dates(TABLE_V3)
    assert set(_d_rows(reader, TABLE_V3)["delisting_basis"]) == {"REPLACEMENT"}
    # a window ending on D's own last session is COMPLETE and right: no run counts a mismatch
    assert [r.stats["delisting_mismatch"] for r in reader.runs("outcomes")] == [0] * 6


def test_a_late_event_rewrites_only_the_v3_row_on_the_recheck() -> None:
    writer, reader, days = _store()
    compute_outcomes(task_ctx(writer), days[-1])
    assert set(_d_rows(reader, TABLE_V3)["delisting_basis"]) == {"NO_EVENT"}
    before = _outcomes(reader, TABLE)
    _events(writer, days, days[-4], days[-3])  # the snapshot arrives after the first night
    record = compute_outcomes(task_ctx(writer), days[-1])
    assert record.stats["delisting_snapshot"] == days[-1].isoformat()
    pd.testing.assert_frame_equal(before, _outcomes(reader, TABLE))  # v2 rows did not change
    assert set(_d_rows(reader, TABLE_V3)["delisting_basis"]) == {"REPLACEMENT"}


def test_an_event_is_a_conflict_only_against_the_listing_historys_last_day() -> None:
    writer, _reader, days = _listing_store()  # Z's listing ends on days[-4]
    _events(writer, days, days[-4], days[-1], iid=Z)
    assert compute_outcomes(task_ctx(writer), days[-1]).stats["delisting_conflicts"] == 0
    other, _reader, days = _listing_store()
    _events(other, days, days[-5], days[-1], iid=Z)
    assert compute_outcomes(task_ctx(other), days[-1]).stats["delisting_conflicts"] == 1


def test_a_reference_date_after_the_last_bar_is_not_a_conflict() -> None:
    writer, _reader, days = _store()  # the reference says D left on days[-2], its last bar days[-4]
    _events(writer, days, days[-4], days[-1])
    assert compute_outcomes(task_ctx(writer), days[-1]).stats["delisting_conflicts"] == 0


def test_a_bar_after_the_event_or_a_wrong_last_bar_is_a_mismatch() -> None:
    bars = _bars({"EQ:D": [50, 45, 40, 41, 42], "EQ:F": [50, 45, None, None, None]})
    events = {"EQ:D": [(W.sessions[2], -0.5, "REPLACEMENT")],
              "EQ:F": [(W.sessions[3], -0.5, "REPLACEMENT")]}  # fmt: skip
    rows, _ = window_rows(bars, W, {"EQ:D", "EQ:F"}, None, {"EQ:F": W.sessions[2]}, events=events)
    assert unapplied_delistings(rows, W, events) == 2


def test_acceptance_checks_both_tables() -> None:
    writer, reader, days = _store()
    record = compute_outcomes(task_ctx(writer), days[-1])
    assert record.stats["tables"] == [TABLE, TABLE_V3]
    settings = task_ctx(writer).settings
    assert [c.status for c in check_outcomes(reader, days[-1], settings)] == ["PASS"]


@pytest.mark.parametrize(
    ("status", "basis", "value", "problem"),
    [
        ("DELISTED", "REPLACEMENT", -1.0, "above -1"),
        ("DELISTED", None, None, "set on a DELISTED row"),
        ("COMPLETE", "NO_EVENT", None, "set on a DELISTED row"),
        ("DELISTED", "NO_EVENT", -0.3, "exactly where"),
        ("DELISTED", "OTC_CLOSE", None, "exactly where"),
        ("DELISTED", "BOGUS", -0.3, "one of"),
    ],
)
def test_the_v3_schema_checks_the_basis_and_the_return(
    status: str, basis: str | None, value: float | None, problem: str
) -> None:
    frame = _v3_frame(status, basis, value)
    with pytest.raises(DataValidationError, match=problem):
        validate_frame(TABLE_V3, frame)


def test_the_v3_schema_accepts_the_valid_rows() -> None:
    for status, basis, value in [("DELISTED", "REPLACEMENT", -0.55), ("DELISTED", "NO_EVENT", None),
                                 ("COMPLETE", None, None)]:  # fmt: skip
        validate_frame(TABLE_V3, _v3_frame(status, basis, value))


def _v3_frame(status: str, basis: str | None, value: float | None) -> pd.DataFrame:
    day = date(2026, 10, 5)
    return pd.DataFrame(
        [{"instrument_id": "EQ:A", "ts": pd.Timestamp(day, tz="UTC"), "horizon_sessions": 5,
          "window_end": date(2026, 10, 12), "benchmark": "SPY", "fwd_return": -0.1,
          "fwd_excess_return": -0.1, "fwd_max_return": 0.0, "fwd_max_drawdown": 0.1,
          "fwd_realised_vol": 0.2, "outcome_status": status, "outcome_reason": None,
          "delisting_return": value, "delisting_basis": basis, "session_date": day,
          "knowledge_ts": pd.Timestamp("2026-10-13", tz="UTC"), "source": "outcomes",
          "run_id": "r"}]
    )  # fmt: skip
