"""Legs, reads logs and outcome reads as rows (ADR 0063): each encodes to a dict of declared
columns and decodes back exactly (the random draws as float32), also after a round trip through a
store, where lists come back as arrays and nulls as None or NaN. A v2 leg's picks (ADR 0064) keep
their unknowns as None, never 0; a v1 row has none."""

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
from algotrade.services.evaluation.cross_section.measures import (
    UNCOUNTED_BAND,
    Pick,
    SessionStat,
)
from algotrade.services.evaluation.cross_section.random_picks import RandomStat, SectorDraws
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.edge_schemas import EDGE_LEGS
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.result_writer import ResultWriter

D = date(2026, 9, 1)
S = date(2026, 9, 2)
AS_OF = datetime(2026, 10, 5, tzinfo=UTC)
NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


# Every kind of pick: counted ones (in order, the stat's pick_values) and excluded ones, with
# unknown scores, gross values, dips, ADVs and references as None.
PICKS = (
    Pick("EQ:A", 1, "", 0.1, True, False, 3.5, 0.11, 0.02, 2.5e7, 0.31, True),
    Pick("EQ:B", 2, "no_entry_bar", score=3.1, adv=None),
    Pick("EQ:C", 3, "", -0.2, False, True, None, None, None, 1e6, 0.29, False),
    Pick("EQ:D", 4, "unmeasured", score=2.0, drawdown=None, adv=4e6),
    Pick("EQ:E", 5, "", 0.35, True, False, 1.0, 0.36, 0.0, None, None, None),
)


def stat(**changes: Any) -> SessionStat:
    base = SessionStat(
        session=D, regime="CALM", pick_values=(0.1, -0.2, 0.35), pick_hits=2,
        rest=(17, 0.0123, 0.456), base_hits=9, top_decile=0.4, spread=0.7,
        deciles=(0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2, -0.3, -0.35, -0.3), ranked=20, unscored=1,
        excluded_missing=1, excluded_unmeasured=2, unmeasured_base=3, delisted=1,
        pre_snapshot=True, outside_universe=4, no_entry_bar=2, pick_reference=(0.31, 0.29),
        pick_touches=1, no_implied_vol=1, implied_stored=True, picks=PICKS,
        base_hits_at=(9, 8, 8, 6), pick_hits_at=(2, 2, 1, 1),
    )  # fmt: skip
    return replace(base, **changes)


def draws(n: int = 4) -> RandomStat:
    rng = np.random.default_rng(3)
    strat = SectorDraws(2, rng.normal(size=n), np.round(rng.uniform(0, 2, size=n)))
    return RandomStat(D, 3, rng.normal(size=n), np.round(rng.uniform(0, 3, size=n)), 20, 9, strat)


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
        assert (a.random.sector is None) == (b.random.sector is None)
        if a.random.sector is not None and b.random.sector is not None:
            assert a.random.sector.picks == b.random.sector.picks
            np.testing.assert_array_equal(a.random.sector.value_sums, b.random.sector.value_sums)
            np.testing.assert_array_equal(a.random.sector.hit_sums, b.random.sector.hit_sums)


def test_the_sector_stratified_draws_round_trip_as_float32_and_a_v2_row_has_none() -> None:
    original = leg()
    row = encode_leg(original, "site", "drift")
    back = decode_leg(row)
    assert original.random is not None and original.random.sector is not None
    assert back.random is not None and back.random.sector is not None
    assert back.random.sector.picks == 2
    np.testing.assert_array_equal(
        back.random.sector.value_sums,
        original.random.sector.value_sums.astype(np.float32).astype(np.float64),
    )
    bare = {k: v for k, v in row.items() if not k.startswith("strat_")}  # a row from leg v2
    old = decode_leg(bare)
    assert old.random is not None and old.random.sector is None and old.random.stratified() is None


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
        {
            "stat": stat(
                top_decile=None,
                spread=None,
                deciles=(),
                pick_values=(),
                pick_reference=(),
                picks=(),
                base_hits_at=(),
                pick_hits_at=(),
            )
        },
        {"stat": SessionStat(session=D, regime="UNKNOWN", excluded_coverage=1)},
    ],
)
def test_nulls_empty_lists_and_absent_draws_survive(changes: dict[str, Any]) -> None:
    original = leg(**changes)
    assert_same(decode_leg(encode_leg(original, "site", "drift")), _float32(original))


def test_a_v1_row_has_no_picks_and_a_corrupt_v2_row_fails() -> None:
    row = encode_leg(leg(), "site", "drift")
    v1 = {k: v for k, v in row.items() if not k.startswith("pick_") or k == "pick_values"}
    v1 |= {"pick_hits": row["pick_hits"], "pick_touches": row["pick_touches"]}
    v1 |= {"pick_reference": row["pick_reference"]}
    old = decode_leg({**v1, "base_hits_at": None, "pick_hits_at": None})
    assert (old.stat.picks, old.stat.base_hits_at, old.stat.pick_hits_at) == ((), (), ())
    with pytest.raises(ValueError, match="counted picks"):
        decode_leg({**row, "pick_values": [0.1]})


def _float32(record: LegRecord) -> LegRecord:
    """``record`` as stored: the draws rounded to float32."""
    if record.random is None:
        return record
    r = record.random

    def round32(a: Any) -> Any:
        return a.astype(np.float32).astype(np.float64)

    sector = r.sector and SectorDraws(r.sector.picks, round32(r.sector.value_sums),
                                      round32(r.sector.hit_sums))  # fmt: skip
    rounded = RandomStat(
        r.session, r.picks, round32(r.value_sums), round32(r.hit_sums), r.eligible, r.base_hits,
        sector,
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


def test_a_long_short_leg_keeps_its_short_names_values_apart_and_an_absent_field_is_long() -> None:
    """Outcome sides: the long leg's counted values are ``pick_values``, the short leg's
    ``short_values``; the flag says which side a pick is. A leg of any other side has no
    ``short_values`` (null, not empty) and reads back as it was written."""
    picks = (
        Pick("EQ:A", 1, "", 0.1, True, False, 3.5, 0.11, 0.02, 2.5e7),
        Pick("EQ:B", 2, "no_entry_bar", score=3.1),
        Pick("EQ:C", 1, "", 0.2, True, False, -3.0, -0.2, 0.0, 9e6, side="short"),
        Pick("EQ:D", 2, "", -0.05, False, False, -3.1, 0.05, 0.0, 8e6, side="short"),
    )
    spread = leg(stat=stat(pick_values=(0.1,), short_values=(0.2, -0.05), picks=picks))
    row = encode_leg(spread, "site", "drift")
    assert row["short_values"] == [0.2, -0.05]
    back = decode_leg(row).stat
    assert back == spread.stat
    assert [(p.instrument_id, p.side, p.value) for p in back.picks] == [
        ("EQ:A", "long", 0.1), ("EQ:B", "long", None), ("EQ:C", "short", 0.2),
        ("EQ:D", "short", -0.05),
    ]  # fmt: skip
    plain = encode_leg(leg(), "site", "drift")
    assert plain["short_values"] is None and decode_leg(plain).stat.short_values is None
    legacy = {k: v for k, v in plain.items() if k != "short_values"}  # a row from before sides
    assert decode_leg(legacy).stat == leg().stat
    empty = leg(stat=stat(pick_values=(), short_values=(), picks=()))
    assert decode_leg(encode_leg(empty, "site", "drift")).stat.short_values == ()  # not None


def test_a_short_leg_is_all_short_picks_with_their_values_in_pick_values() -> None:
    picks = (Pick("EQ:C", 1, "", 0.2, True, side="short"), Pick("EQ:D", 2, "", -0.05, side="short"))
    short = leg(stat=stat(pick_values=(0.2, -0.05), picks=picks, pick_hits=1))
    back = decode_leg(encode_leg(short, "site", "drift")).stat
    assert back == short.stat and all(p.side == "short" for p in back.picks)
    assert back.short_values is None


def test_a_buy_hold_band_round_trips_and_a_leg_without_one_stores_nothing_new() -> None:
    """Leg v4: the band's names as ``band_*`` lists, a name with no counted value as a null value
    (never 0); a leg of an edge without ``hold_rank`` has null columns and reads back with none."""
    below = (
        Pick("EQ:F", 6, "", 0.05),
        Pick("EQ:G", 7, UNCOUNTED_BAND, None),
        Pick("EQ:H", 8, "", -0.02),
    )
    banded = leg(stat=stat(band=below))
    row = encode_leg(banded, "site", "drift")
    assert row["band_ids"] == ["EQ:F", "EQ:G", "EQ:H"] and row["band_ranks"] == [6, 7, 8]
    assert row["band_values"] == [0.05, None, -0.02]
    assert decode_leg(row).stat == banded.stat and decode_leg(row).stat.band == below
    plain = encode_leg(leg(), "site", "drift")
    assert (plain["band_ids"], plain["band_ranks"], plain["band_values"]) == (None, None, None)
    assert decode_leg(plain).stat.band == ()
    legacy = {k: v for k, v in plain.items() if not k.startswith("band_")}  # a leg before v4
    assert decode_leg(legacy).stat.band == ()
    assert {"band_ids", "band_ranks", "band_values"} <= {c.name for c in EDGE_LEGS.columns}


def test_a_portfolio_book_round_trips_and_every_other_leg_stores_nothing_new() -> None:
    """Leg v5 (ADR 0074): the book's weights as ``weight_ids`` / ``weight_values`` and a session
    with no value as ``portfolio_reason``; null columns in every other leg, which read back with
    no book and no reason (a leg from before v5 has no such columns at all)."""
    book = (("EQ:A", 0.25), ("EQ:B", 0.5), ("CASH", 0.25))
    held = leg(stat=stat(pick_values=(0.01,), pick_hits=1, picks=(), weights=book))
    row = encode_leg(held, "site", "drift")
    assert row["weight_ids"] == ["EQ:A", "EQ:B", "CASH"]
    assert row["weight_values"] == [0.25, 0.5, 0.25] and row["portfolio_reason"] is None
    assert decode_leg(row).stat == held.stat and decode_leg(row).stat.weights == book
    lost = leg(stat=stat(excluded_coverage=1, portfolio_reason="no_benchmark_row:AGG"))
    again = decode_leg(encode_leg(lost, "site", "drift")).stat
    assert again.portfolio_reason == "no_benchmark_row:AGG" and again.weights == ()
    plain = encode_leg(leg(), "site", "drift")
    assert (plain["weight_ids"], plain["weight_values"], plain["portfolio_reason"]) == (
        None,
        None,
        None,
    )
    legacy = {k: v for k, v in plain.items() if not k.startswith(("weight_", "portfolio_"))}
    assert decode_leg(legacy).stat.weights == ()
    assert {"weight_ids", "weight_values", "portfolio_reason"} <= {
        c.name for c in EDGE_LEGS.columns
    }


def test_the_overlay_figures_of_a_book_round_trip_and_default_to_null() -> None:
    """ADR 0074 amendment: ``book_vol`` and ``risk_off`` are nullable columns of the leg (no
    version bump): stored when an overlay ran, null otherwise and in a leg written before them."""
    held = leg(stat=stat(pick_values=(0.01,), pick_hits=1, picks=(), book_vol=0.2, risk_off=0.5))
    row = encode_leg(held, "site", "drift")
    assert (row["book_vol"], row["risk_off"]) == (0.2, 0.5)
    assert decode_leg(row).stat == held.stat
    plain = encode_leg(leg(), "site", "drift")
    assert (plain["book_vol"], plain["risk_off"]) == (None, None)
    again = decode_leg(plain).stat
    assert (again.book_vol, again.risk_off) == (None, None)
    legacy = {k: v for k, v in plain.items() if k not in ("book_vol", "risk_off")}
    assert decode_leg(legacy).stat.book_vol is None
    assert {"book_vol", "risk_off"} <= {c.name for c in EDGE_LEGS.columns}


CONTRACT_PICK = Pick(
    "EQ:K", 1, "", 0.03, True, exit_session=date(2026, 9, 4), exit_kind="TAKE_PROFIT",
    capital=95.0, roc_gross=0.021, roc=0.019, adverse=0.04, price_source="option_history",
    outcome_licence="personal",
)  # fmt: skip


def test_a_pick_with_the_contract_fields_round_trips_losslessly_and_a_v4_row_has_none() -> None:
    """Leg v5 (ADR 0088, E6a): every pick's contract fields as aligned ``pick_*`` lists, an
    unknown one as null (never 0); a row from before them decodes with None on every pick."""
    bare = Pick("EQ:L", 2, "no_entry_bar")
    full = leg(stat=stat(pick_values=(0.03,), pick_hits=1, picks=(CONTRACT_PICK, bare)))
    row = encode_leg(full, "site", "drift")
    assert row["pick_exit"] == [date(2026, 9, 4), None] and row["pick_roc"] == [0.019, None]
    assert row["pick_source"] == ["option_history", None]
    assert decode_leg(row).stat.picks == (CONTRACT_PICK, bare)
    v4 = {k: v for k, v in row.items() if k not in CONTRACT_COLUMNS}
    old = decode_leg(v4).stat.picks
    assert old[0] == replace(CONTRACT_PICK, **dict.fromkeys(CONTRACT_FIELDS))
    assert all(getattr(p, f) is None for p in old for f in CONTRACT_FIELDS)


def test_the_contract_fields_survive_a_store(backend: Backend) -> None:
    full = leg(
        stat=stat(pick_values=(0.03,), pick_hits=1, picks=(CONTRACT_PICK, Pick("EQ:L", 2, "x")))
    )
    write = ResultWriter(backend)
    rows = [encode_leg(full, "site", "drift")]
    with write.publishing("r1", NOW):
        write_legs(write, "r1", legs_frame(rows, "r1", NOW))
    found = read_legs(StoreReader(backend), "site", "drift", D, D)
    stored = found.legs[full.key, full.edge_variant, full.variant, full.horizon, D]
    assert stored.stat.picks == full.stat.picks  # dates, strings and floats, nulls as None


CONTRACT_FIELDS = (
    "exit_session", "exit_kind", "capital", "roc_gross", "roc", "adverse", "price_source",
    "outcome_licence",
)  # fmt: skip
CONTRACT_COLUMNS = (
    "pick_exit", "pick_exit_kind", "pick_source", "pick_licence", "pick_capital",
    "pick_roc_gross", "pick_roc", "pick_adverse",
)  # fmt: skip
