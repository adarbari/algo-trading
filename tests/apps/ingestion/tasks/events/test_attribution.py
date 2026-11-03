"""The ``attribution`` task over a stored ``event_reaction`` rollup and 8-K filings: the session's
big movers get the cause their 8-K names, a quiet name or an exhibit-only filing gets none, a
session with no rollup is skipped, and a rerun stores the same rows."""

from datetime import date

import pandas as pd

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.events import attribution
from algotrade_ingestion.tasks.events.attribution import TABLE, ingest_attribution
from tests.helpers.ingest_fakes import task_ctx
from tests.helpers.stored_frames import stamped

SESSION = date(2026, 10, 5)  # a Monday
BIG, NEWS, QUIET, BARE = "EQ:BIG", "EQ:NEWS", "EQ:QUIET", "EQ:BARE"


def _store(with_rollup: bool = True) -> StoreWriter:
    writer = StoreWriter(MemoryBackend())
    if with_rollup:
        rows = [
            {"instrument_id": BIG, "big_move_5pct_today": 1.0, "big_move_2x_today": 1.0},
            {"instrument_id": NEWS, "big_move_5pct_today": 0.0, "big_move_2x_today": 1.0},
            {"instrument_id": QUIET, "big_move_5pct_today": 0.0, "big_move_2x_today": 0.0},
            {"instrument_id": BARE, "big_move_5pct_today": 1.0, "big_move_2x_today": None},
        ]
        writer.write_table(attribution.REACTION, SESSION, "rr", stamped(rows, SESSION, "rr"))
    # accepted Friday after the close: its acceptance session is Monday
    filing = lambda iid, items, acc, form="8-K": {  # noqa: E731
        "instrument_id": iid, "ts": pd.Timestamp("2026-10-02T21:30:00Z"), "known_from": SESSION,
        "cik": "1", "form": form, "accession": acc, "filing_date": date(2026, 10, 5),
        "items": items,
    }  # fmt: skip
    filings = [
        filing(BIG, "2.02,9.01", "a1"),
        filing(NEWS, "9.01", "a2"),  # an exhibit alone: no cause
        filing(QUIET, "2.02", "a3"),  # filed, but the name did not move big
        filing(BARE, "5.02", "a4", form="10-Q"),  # not an 8-K
    ]
    writer.write_table(attribution.FILINGS, SESSION, "f", stamped(filings, SESSION, "f"))
    return writer


def _stored(writer: StoreWriter) -> pd.DataFrame:
    frame = StoreReader(writer._backend).table(TABLE, SESSION)
    assert frame is not None
    return frame.set_index("instrument_id")


def test_the_big_mover_with_an_8k_gets_its_cause_and_the_rest_get_none() -> None:
    writer = _store()
    record = ingest_attribution(task_ctx(writer), SESSION)
    out = _stored(writer)
    assert list(out.index) == [BIG]
    row = out.loc[BIG]
    assert (row["cause_class"], row["source"]) == ("results", "filing")
    assert row["evidence_ref"] == "a1" and row["confidence"] == 0.9
    assert pd.Timestamp(row["known_from"]).date() == SESSION  # public from its reaction session
    assert record.stats["movers"] == 3 and record.stats["rows"] == 1  # BIG, NEWS, BARE moved


def test_big_movers_read_either_flag_and_a_null_flag_is_no_move() -> None:
    frame = pd.DataFrame(
        {"instrument_id": ["a", "b", "c"], "big_move_5pct_today": [1.0, None, 0.0],
         "big_move_2x_today": [0.0, 1.0, None]}
    )  # fmt: skip
    assert attribution.big_movers(frame) == {"a", "b"}


def test_a_session_without_the_rollup_is_skipped_not_empty() -> None:
    writer = _store(with_rollup=False)
    record = ingest_attribution(task_ctx(writer), SESSION)
    assert record.stats["movers"] is None and record.stats["rows"] == 0
    assert StoreReader(writer._backend).table(TABLE, SESSION) is None


def test_a_rerun_stores_the_same_rows() -> None:
    writer = _store()
    ingest_attribution(task_ctx(writer), SESSION)
    first = _stored(writer)[["cause_class", "evidence_ref"]]
    ingest_attribution(task_ctx(writer), SESSION)
    pd.testing.assert_frame_equal(_stored(writer)[["cause_class", "evidence_ref"]], first)
