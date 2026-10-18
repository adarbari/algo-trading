"""The ``option-outcomes`` task on stored chains priced by Black-Scholes at a known vol: a window
is written to its start session's partition with ``knowledge_ts`` the latest chain partition it
read (not the write time); a stale chain on a session of the window is an UNMEASURED row with the
session in its reason, never a gap filled from an earlier chain; a window starting before the
first stored chain is not computed (forward-only); one not yet closed is refused; the structures,
tenors and horizons come from the open edge documents; the acceptance check passes on the run's
own rows and fails on a name that has a chain but no row."""

import dataclasses
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.core.time.calendar import close_time, sessions_ending
from algotrade.quant.black_scholes import price
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunStatus
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.schemas import OPTION_PNL_REASONS
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.derived.option_outcomes import (
    TABLE,
    check_option_outcomes,
    compute_option_outcomes,
    windows_wanted,
)
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.rollup_store import store
from tests.helpers.stored_frames import stamped
from tests.unit.config.edges.test_document import document
from tests.unit.config.edges.test_loading import store as edge_store

END = date(2026, 10, 14)
NOW = datetime(2026, 10, 20, tzinfo=UTC)
DAYS = sessions_ending(END, 7)  # the first stored chain is DAYS[0]
EXPIRY = date(2026, 11, 20)
VOL, HALF = 0.30, 0.05
A, B = "EQ:A", "EQ:B"
OUTCOME = {
    "kind": "option_pnl", "horizon_sessions": [2], "benchmark": "none", "tenor_days": 30,
    "start_offset_sessions": 1, "structure": "atm_straddle_long",
}  # fmt: skip


def _configs(**outcome: object) -> MemoryConfigStore:
    doc = document(schedule="every_session", screeners=[], outcome={**OUTCOME, **outcome})
    return edge_store(site__drift=doc)


def _known(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=23)


def _chains(
    skip_status: dict[tuple[str, date], str] | None = None,
) -> tuple[StoreWriter, StoreReader]:
    """A chain per session for A and B (spot 100 + day index), each OK unless overridden."""
    writer, reader = store()
    for i, day in enumerate(DAYS):
        statuses, unders, options = [], [], []
        for name in (A, B):
            spot = 100.0 + i + (5 if name == B else 0)
            status = (skip_status or {}).get((name, day), "OK")
            statuses.append({"instrument_id": name, "symbol": name[3:], "status": status,
                             "tier": "core"})  # fmt: skip
            stamp = pd.Timestamp(_known(day))
            unders.append({"instrument_id": name, "symbol": name[3:], "ts": stamp, "price": spot,
                           "close": spot, "volume": 1e6, "iv30": VOL})  # fmt: skip
            t = (EXPIRY - day).days / 365
            for strike in (95.0, 100.0, 105.0, 110.0):
                for right in ("C", "P"):
                    mid = float(price(spot, strike, t, 0.0, 0.0, VOL, right == "C"))
                    options.append({
                        "instrument_id": f"OPT:{name}:{right}{int(strike)}", "underlying_id": name,
                        "ts": pd.Timestamp(_known(day)), "expiry": EXPIRY, "right": right,
                        "strike": strike, "bid": mid - HALF, "ask": mid + HALF, "volume": 10.0,
                        "open_interest": 100.0, "iv": VOL, "delta": 0.5,
                    })  # fmt: skip
        for table, rows in (("chains/status", statuses), ("chains/underlying_quotes", unders),
                            ("chains/option_quotes", options)):  # fmt: skip
            frame = stamped(rows, day, f"c-{day}", _known(day), "test")
            writer.write_table(table, day, f"c-{day}-{table}", frame)
    return writer, reader


def _ctx(writer: StoreWriter, configs: MemoryConfigStore, clock=lambda: NOW):  # type: ignore[no-untyped-def]
    return dataclasses.replace(task_ctx(writer, clock=clock), configs=configs)


def _rows(reader: StoreReader) -> pd.DataFrame:
    parts = [reader.table(TABLE, d) for d in reader.dates(TABLE)]
    return pd.concat([p for p in parts if p is not None], ignore_index=True)


def test_windows_come_from_the_open_edge_documents() -> None:
    assert windows_wanted(_configs()) == [("atm_straddle", 30, 2)]
    put = _configs(structure="put_short", strike_delta=0.25, horizon_sessions=[2, 5])
    assert windows_wanted(put) == [("put_delta_25", 30, 2), ("put_delta_25", 30, 5)]
    assert windows_wanted(MemoryConfigStore({})) == []


def test_a_window_is_written_to_its_start_partition_known_when_its_exit_chain_was() -> None:
    writer, reader = _chains()
    record = compute_option_outcomes(_ctx(writer, _configs()), END)
    assert record.status == RunStatus.COMPLETE, record.stats
    start = sessions_ending(END, 3)[0]
    part = reader.table(TABLE, start)
    assert part is not None and set(part["instrument_id"]) == {A, B}
    a = part[part["instrument_id"] == A].iloc[0]
    assert (a["structure"], a["tenor_days"], a["horizon_sessions"], a["window_end"]) == (
        "atm_straddle", 30, 2, END,
    )  # fmt: skip
    assert a["outcome_status"] == "COMPLETE" and a["exit_kind"] == "QUOTE"
    assert pd.Timestamp(a["ts"]) == pd.Timestamp(close_time(start))
    assert pd.Timestamp(a["knowledge_ts"]) == pd.Timestamp(_known(END))  # not the write time (NOW)
    assert record.stats["atm_straddle:t30:h2"]["unmeasured"] == 0


def test_a_stale_chain_in_the_window_is_an_unmeasured_row_with_its_session() -> None:
    mid = sessions_ending(END, 2)[0]  # the session before the exit
    writer, reader = _chains({(B, mid): "STALE_DATA: chain is for 2026-10-08"})
    record = compute_option_outcomes(_ctx(writer, _configs()), END)
    rows = _rows(reader)
    rows = rows[rows["window_end"] == END]
    b = rows[rows["instrument_id"] == B].iloc[0]
    assert b["outcome_status"] == "UNMEASURED" and b["outcome_reason"] == f"STALE_CHAIN:{mid}"
    assert pd.isna(b["pnl_per_premium"]) and pd.isna(b["hedged_pnl_per_premium"])
    a = rows[rows["instrument_id"] == A].iloc[0]
    assert a["outcome_status"] == "COMPLETE"  # a stale chain for B costs only B its window
    assert record.stats["atm_straddle:t30:h2"]["reasons"] == {"STALE_CHAIN": 1}
    assert {"STALE_CHAIN"} <= set(OPTION_PNL_REASONS)


def test_a_window_before_the_first_stored_chain_is_not_computed() -> None:
    writer, reader = _chains()
    record = compute_option_outcomes(_ctx(writer, _configs(horizon_sessions=[2, 21])), END)
    assert record.items["atm_straddle:t30:h21"] == "BEFORE_HISTORY"
    assert all(int(h) == 2 for h in _rows(reader)["horizon_sessions"])


def test_a_window_that_has_not_closed_is_refused() -> None:
    writer, _ = _chains()
    early = lambda: close_time(END) - timedelta(hours=1)  # noqa: E731
    with pytest.raises(ValueError, match="has not closed"):
        compute_option_outcomes(_ctx(writer, _configs(), early), END)


def test_the_acceptance_check_passes_and_fails_on_a_name_with_a_chain_but_no_row() -> None:
    writer, reader = _chains()
    ctx = _ctx(writer, _configs())
    compute_option_outcomes(ctx, END)
    (passed,) = check_option_outcomes(reader, END, ctx.settings)
    assert passed.status == "PASS", passed.detail
    # a third name gets an OK chain at the entry after the run: the count no longer matches
    start = sessions_ending(END, 3)[0]
    extra = stamped(
        [{"instrument_id": "EQ:C", "symbol": "C", "status": "OK", "tier": "core"}],
        start, "late", _known(start), "test",
    )  # fmt: skip
    status = reader.table("chains/status", start)
    assert status is not None
    writer.write_table("chains/status", start, "late-status", pd.concat([status, extra]))
    (failed,) = check_option_outcomes(reader, END, ctx.settings)
    assert failed.status == "FAIL" and "OK chains" in failed.detail
    assert check_option_outcomes(reader, date(2026, 10, 15), ctx.settings)[0].status == "FAIL"
