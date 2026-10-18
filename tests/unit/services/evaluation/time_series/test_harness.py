"""The seam: raw returns by period as the partitions held them, a reason (never a value) for
what is missing, symbols through the reference snapshot, the bill known at D."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.services.evaluation.time_series import harness
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.time_series.conftest import (
    AS_OF,
    FIRST,
    SPY_ID,
    H,
    build_world,
    row,
)


def test_returns_come_from_the_partition_at_each_entry_session() -> None:
    w = build_world()
    entries = [p.entry for p in w.periods[:3]]
    got = harness.read_returns(w.reader, [SPY_ID], entries, H, AS_OF)
    assert sorted(got.values) == [(SPY_ID, e) for e in entries] and not got.reasons
    assert all(isinstance(v, float) for v in got.values.values())


def test_a_missing_unmeasured_or_not_yet_known_row_has_a_reason_not_a_value() -> None:
    gone, flagged, late = (p.entry for p in build_world().periods[:3])
    w2 = build_world(
        skip=frozenset({gone}),
        changes={
            flagged: {
                "outcome_status": "UNMEASURED",
                "fwd_return": None,
                "outcome_reason": "BAD_BAR",
                "fwd_max_return": None,
                "fwd_max_drawdown": None,
            }
        },
    )
    got = harness.read_returns(w2.reader, [SPY_ID], [gone, flagged, late], H, AS_OF)
    assert got.reasons[SPY_ID, gone] == harness.NO_OUTCOME
    assert got.reasons[SPY_ID, flagged] == "UNMEASURED:BAD_BAR"
    assert (SPY_ID, late) in got.values
    early = datetime(2026, 10, 3, tzinfo=UTC)  # before the rows were written: invisible
    unseen = harness.read_returns(w2.reader, [SPY_ID], [late], H, early)
    assert unseen.reasons == {(SPY_ID, late): harness.NO_OUTCOME} and not unseen.values


def test_another_horizon_or_benchmark_is_not_read() -> None:
    w = build_world(changes={p.entry: {"horizon_sessions": H + 1} for p in build_world().periods})
    got = harness.read_returns(w.reader, [SPY_ID], [w.periods[0].entry], H, AS_OF)
    assert not got.values


def test_symbols_resolve_through_the_reference_snapshot() -> None:
    w = build_world()
    ids, reasons = harness.resolve_symbols(w.reader, ["SPY", "ZZZZ"], date(2025, 12, 31), AS_OF)
    assert ids == {"SPY": SPY_ID} and reasons == {"ZZZZ": harness.UNKNOWN_SYMBOL}


def test_a_bill_is_left_out_when_no_curve_was_known_at_d() -> None:
    w = build_world()
    assert harness.bill_returns(w.reader, [FIRST], 4, AS_OF) == {}
    rows = [
        {"instrument_id": f"RATE:UST-{t}", "ts": pd.Timestamp(date(2023, 12, 20), tz="UTC"),
         "tenor": t, "tenor_days": d, "rate_par": r, "rate_cont": r}
        for t, d, r in (("1M", 30, 0.04), ("3M", 91, 0.05), ("2Y", 730, 0.06))
    ]  # fmt: skip
    day = date(2023, 12, 20)
    w.writer.write_table("rates/treasury", day, "r1", stamped(rows, day, "r1"))
    got = harness.bill_returns(w.reader, [date(2023, 12, 28), date(2023, 12, 1)], 4, AS_OF)
    assert got == {date(2023, 12, 28): pytest.approx(0.05 * 4 / 252)}  # D before the curve: none
    assert row(FIRST, 0.0)["benchmark"] == harness.BENCHMARK
