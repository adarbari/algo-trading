"""Legs, reads logs and outcome reads as rows (ADR 0063): each encodes to a dict of declared
columns and decodes back exactly (the random draws as float32), also after a round trip through a
store, where lists come back as arrays and nulls as None or NaN."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from algotrade.data import ReadRecord, StoreReader
from algotrade.services.evaluation.cross_section.legs.rows import (
    LEG,
    OUTCOME,
    READS,
    DayReads,
    LegRecord,
    OutcomeRead,
    decode_frame,
    decode_leg,
    decode_outcome,
    decode_reads,
    encode_leg,
    encode_outcome,
    encode_reads,
)
from algotrade.services.evaluation.cross_section.legs.store import (
    legs_frame,
    read_legs,
    write_legs,
)
from algotrade.services.evaluation.cross_section.measures import SessionStat
from algotrade.services.evaluation.cross_section.random_picks import RandomStat
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.edge_schemas import EDGE_LEGS
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter

D = date(2026, 9, 1)
S = date(2026, 9, 2)
AS_OF = datetime(2026, 10, 5, tzinfo=UTC)
NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


def stat(**changes: Any) -> SessionStat:
    base = SessionStat(
        session=D, regime="CALM", pick_values=(0.1, -0.2, 0.35), pick_hits=2,
        rest=(17, 0.0123, 0.456), base_hits=9, top_decile=0.4, spread=0.7,
        deciles=(0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.35, -0.3), ranked=20, unscored=1,
        excluded_missing=1, excluded_unmeasured=2, unmeasured_base=3, delisted=1,
        pre_snapshot=True, outside_universe=4, no_entry_bar=2, pick_reference=(0.31, 0.29),
        pick_touches=1, no_implied_vol=1, implied_stored=True,
    )  # fmt: skip
    return replace(base, **changes)


def draws(n: int = 4) -> RandomStat:
    rng = np.random.default_rng(3)
    return RandomStat(D, 3, rng.normal(size=n), np.round(rng.uniform(0, 3, size=n)), 20, 9)


def leg(**changes: Any) -> LegRecord:
    base = LegRecord(
        key="k" * 64, trial_hash="t" * 64, edge_variant="main", variant="momo", horizon=2,
        entry=S, stat=stat(), outcomes_as_of=AS_OF, random=draws(),
        event_ids=("EQ:A", "EQ:B"), lost_table=None, snapshot=date(2026, 8, 28), outcome_seq=7,
    )  # fmt: skip
    return replace(base, **changes)


def assert_same(a: LegRecord, b: LegRecord) -> None:
    assert (a.stat, a.key, a.trial_hash, a.entry, a.snapshot, a.outcome_seq) == (
        b.stat, b.key, b.trial_hash, b.entry, b.snapshot, b.outcome_seq
    )  # fmt: skip
    assert (a.edge_variant, a.variant, a.horizon, a.event_ids, a.lost_table) == (
        b.edge_variant, b.variant, b.horizon, b.event_ids, b.lost_table
    )  # fmt: skip
    assert a.outcomes_as_of == b.outcomes_as_of and a.day == b.day
    assert (a.random is None) == (b.random is None)
    if a.random is not None and b.random is not None:
        assert (a.random.picks, a.random.eligible, a.random.base_hits) == (
            b.random.picks, b.random.eligible, b.random.base_hits
        )  # fmt: skip
        np.testing.assert_array_equal(a.random.value_sums, b.random.value_sums)
        np.testing.assert_array_equal(a.random.hit_sums, b.random.hit_sums)


def test_a_leg_round_trips_exactly_but_for_the_draws_as_float32() -> None:
    original = leg()
    back = decode_leg(encode_leg(original, "site", "drift"))
    assert back.stat == original.stat  # every SessionStat field, tuples and moments included
    assert back.random is not None and original.random is not None
    assert back.random.value_sums.dtype == np.float64
    np.testing.assert_array_equal(
        back.random.value_sums, original.random.value_sums.astype(np.float32).astype(np.float64)
    )
    assert not np.array_equal(back.random.value_sums, original.random.value_sums)  # it did round
    np.testing.assert_array_equal(back.random.hit_sums, original.random.hit_sums)  # integers


@pytest.mark.parametrize(
    "changes",
    [
        {"random": None},
        {"event_ids": None},
        {"event_ids": ()},
        {"lost_table": "rollups/instrument/x@v1", "snapshot": None},
        {"stat": stat(top_decile=None, spread=None, deciles=(), pick_values=(), pick_reference=())},
        {"stat": SessionStat(session=D, regime="UNKNOWN", excluded_coverage=1)},
    ],
)
def test_nulls_empty_lists_and_absent_draws_survive(changes: dict[str, Any]) -> None:
    original = leg(**changes)
    assert_same(decode_leg(encode_leg(original, "site", "drift")), _float32(original))


def _float32(record: LegRecord) -> LegRecord:
    """``record`` as stored: the draws rounded to float32."""
    if record.random is None:
        return record
    r = record.random
    rounded = RandomStat(
        r.session, r.picks, r.value_sums.astype(np.float32).astype(np.float64),
        r.hit_sums.astype(np.float32).astype(np.float64), r.eligible, r.base_hits,
    )  # fmt: skip
    return replace(record, random=rounded)


def test_reads_and_outcome_rows_round_trip() -> None:
    reads = DayReads(
        D,
        (
            ReadRecord("universe", D, D, "rows"),
            ReadRecord("rollups/x@v1", D, D, "rows"),
            ReadRecord("regime", date(2026, 1, 2), D, "dates", "abc123"),
        ),
        41,
        {"today_flag": 5, "proxy": 2},
        {"today_flag": 7},
    )
    assert decode_reads(encode_reads(reads, "site", "drift")) == reads
    bare = DayReads(D, (), None)
    assert decode_reads(encode_reads(bare, "site", "drift")) == bare
    seen = OutcomeRead(D, "main", 2, S, AS_OF, 17)
    assert decode_outcome(encode_outcome(seen, "site", "drift")) == seen
    none = OutcomeRead(D, "cheap", 5, S, AS_OF, None)
    assert decode_outcome(encode_outcome(none, "site", "drift")) == none


def test_every_row_kind_only_uses_declared_columns_and_its_own_key() -> None:
    rows = [
        encode_leg(leg(), "site", "drift"),
        encode_reads(DayReads(D, (), 1), "site", "drift"),
        encode_outcome(OutcomeRead(D, "main", 2, S, AS_OF, 1), "site", "drift"),
    ]
    declared = {c.name for c in EDGE_LEGS.columns}
    for row in rows:
        assert set(row) <= declared
        assert all(row[k] is not None for k in EDGE_LEGS.key) and row["session_date"] == D
    assert [r["row_kind"] for r in rows] == [LEG, READS, OUTCOME]
    assert (rows[1]["leg_key"], rows[1]["variant"], rows[1]["horizon_sessions"]) == ("", "", 0)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Backend:
    return MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path)


def test_rows_survive_a_store_and_come_back_decoded(backend: Backend) -> None:
    kept = [
        leg(),
        leg(variant="base", random=None, event_ids=None),
        leg(variant="gone", lost_table="rollups/x@v1", snapshot=None,
            stat=SessionStat(session=D, regime="UNKNOWN", excluded_coverage=1)),
        leg(edge_variant="cheap", event_ids=(), stat=stat(top_decile=None, deciles=())),
    ]  # fmt: skip
    rows = [encode_leg(r, "site", "drift") for r in kept]
    reads = DayReads(D, (ReadRecord("universe", D, D, "rows"),), 9, {"proxy": 1}, {})
    seen = OutcomeRead(D, "main", 2, S, AS_OF, 4)
    rows += [encode_reads(reads, "site", "drift"), encode_outcome(seen, "site", "drift")]
    rows.append(encode_leg(leg(variant="other"), "someone", "drift"))  # another user's
    write = ResultWriter(backend)
    with write.publishing("r1", NOW):
        assert write_legs(write, "r1", legs_frame(rows, "r1", NOW)) == 1  # one partition: D
    found = read_legs(StoreReader(backend), "site", "drift", D, D)
    assert len(found.legs) == 4 and found.reads == {D: reads}
    assert found.outcomes == {("main", 2, D): seen}
    for original in kept:
        stored = found.legs[
            original.key, original.edge_variant, original.variant, original.horizon, D
        ]
        assert_same(stored, _float32(original))
        assert stored.known == NOW  # stamped by the run
    assert read_legs(StoreReader(backend), "site", "drift", D, D, as_of=AS_OF).legs == {}


def test_nothing_stored_reads_as_nothing(backend: Backend) -> None:
    assert read_legs(StoreReader(backend), "site", "drift", D, S).legs == {}
    assert decode_frame(pd.DataFrame()) == decode_frame(None)
