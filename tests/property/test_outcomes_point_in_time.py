"""Point in time for forward outcomes (ADR 0053): whatever window end the ``outcomes`` task runs
for, and whenever it runs after that session's close, every stored row's ``knowledge_ts`` is at
or after the close of its ``window_end``, which is exactly ``horizon_sessions`` exchange sessions
after its start session; a run before the close writes nothing."""

from datetime import timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algotrade.core.time.calendar import close_time, sessions_ending
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.outcomes import TABLE, compute_outcomes
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import SPY, series, store, write_bars, write_rows
from tests.helpers.stored_frames import universe_rows

N = 70


def _store() -> tuple[StoreWriter, StoreReader, list]:
    writer, reader = store()
    days = write_bars(writer, {"EQ:A": series(N), SPY: series(N, seed=3)})
    write_rows(writer, "instruments/reference", days[0], [
        {"instrument_id": iid, "symbol": s, "asset_class": "EQ", "security_type": "COMMON_STOCK",
         "multiplier": 1.0, "status": "ACTIVE"} for s, iid in (("A", "EQ:A"), ("SPY", SPY))
    ])  # fmt: skip
    write_rows(writer, "universe", days[0], universe_rows(["A"]))
    return writer, reader, days


@settings(max_examples=12, deadline=None)
@given(end_back=st.integers(0, 15), minutes=st.integers(-180, 6000))
def test_rows_are_never_known_before_their_window_closes(end_back: int, minutes: int) -> None:
    writer, reader, days = _store()
    end = days[-1 - end_back]
    now = close_time(end) + timedelta(minutes=minutes)
    ctx = task_ctx(writer, clock=lambda: now)
    if minutes < 0:
        with pytest.raises(ValueError, match="has not closed"):
            compute_outcomes(ctx, end)
        assert reader.dates(TABLE) == []
        return
    compute_outcomes(ctx, end)
    for day in reader.dates(TABLE):
        part = reader.table(TABLE, day)
        assert part is not None
        for _, row in part.iterrows():
            window_end = pd.Timestamp(row["window_end"]).date()
            assert pd.Timestamp(row["knowledge_ts"]) >= pd.Timestamp(close_time(window_end))
            assert sessions_ending(window_end, int(row["horizon_sessions"]) + 1)[0] == day
