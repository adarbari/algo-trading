"""The weekly audit's comparison (ADR 0063): a full run's legs against the stored ones find
exactly the legs whose content changed or that are not stored, and none for what a run stamps."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

from algotrade.services.evaluation.cross_section.legs.audit import (
    ABSENT,
    differing_legs,
    keep_differing,
)
from algotrade.services.evaluation.cross_section.legs.rows import (
    READS,
    LegRecord,
    decode_leg,
    encode_leg,
)
from algotrade.services.evaluation.cross_section.measures import SessionStat

AS_OF = datetime(2026, 10, 5, tzinfo=UTC)


def leg(day: date, **stat: Any) -> LegRecord:
    base = SessionStat(
        session=day, regime="CALM", pick_values=(0.1, float("nan")), pick_hits=1,
        rest=(5, 0.01, 0.2), base_hits=2, top_decile=None, spread=None, deciles=(0.1,) * 10,
        ranked=7, unscored=0,
    )  # fmt: skip
    return LegRecord(
        key="k", trial_hash="t", edge_variant="main", variant="momo", horizon=1,
        entry=day + timedelta(days=1), stat=replace(base, **stat), outcomes_as_of=AS_OF,
        outcome_seq=3,
    )  # fmt: skip


DAYS = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]


def key(record: LegRecord) -> Any:
    return (record.key, record.edge_variant, record.variant, record.horizon, record.day)


def stored_of(*records: LegRecord) -> dict[Any, LegRecord]:
    # as the store gives them back: through a row
    return {key(r): decode_leg(encode_leg(r, "site", "e")) for r in records}


def rows_of(*records: LegRecord) -> list[dict[str, Any]]:
    return [encode_leg(r, "site", "e") for r in records]


def test_identical_legs_do_not_differ_though_nan_and_the_stamps_do() -> None:
    legs = [leg(d) for d in DAYS]
    later = [replace(r, outcomes_as_of=AS_OF + timedelta(days=1), outcome_seq=9) for r in legs]
    assert differing_legs(rows_of(*later), stored_of(*legs), "site", "e") == []


def test_only_the_changed_legs_are_found_with_their_columns() -> None:
    old = [leg(d) for d in DAYS]
    fresh = [old[0], leg(DAYS[1], pick_hits=2, ranked=8), old[2]]
    found = differing_legs(rows_of(*fresh), stored_of(*old), "site", "e")
    assert [(d.key[4], d.columns) for d in found] == [(DAYS[1], ("pick_hits", "ranked"))]
    assert "momo h1 2026-09-02" in found[0].describe()


def test_a_leg_not_stored_is_absent_and_a_stored_leg_the_run_lacks_is_ignored() -> None:
    old = [leg(DAYS[0]), leg(DAYS[2])]
    found = differing_legs(rows_of(leg(DAYS[0]), leg(DAYS[1])), stored_of(*old), "site", "e")
    assert [(d.key[4], d.columns) for d in found] == [(DAYS[1], (ABSENT,))]


def test_the_rows_kept_are_every_row_of_a_session_with_a_differing_leg() -> None:
    rows = [*rows_of(*(leg(d) for d in DAYS)), {"row_kind": READS, "session_date": DAYS[1]}]
    found = differing_legs(rows, stored_of(leg(DAYS[0]), leg(DAYS[2])), "site", "e")
    kept = keep_differing(rows, found)
    assert [r["session_date"] for r in kept] == [DAYS[1], DAYS[1]]
