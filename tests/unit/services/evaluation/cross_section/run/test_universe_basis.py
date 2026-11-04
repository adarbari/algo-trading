"""The ``universe_basis`` predicate (ADR 0087 decision 6): ``free`` only with no gap, every
threshold flips exactly its own gap at its boundary (met at equality), a v2 read is always
``survivors``, and the gaps come out sorted."""

from dataclasses import replace
from datetime import date

import pytest

from algotrade.config.edges.universe_basis import UniverseBasisLimits
from algotrade.data.listings.basis import BasisCounts
from algotrade.services.evaluation.cross_section.run.universe_basis import (
    FREE,
    SURVIVORS,
    universe_basis,
)
from algotrade.storage.tables.schemas import FORWARD_RETURNS, FORWARD_RETURNS_V3

LIMITS = UniverseBasisLimits()  # 1%, 98%, 5%, 5%
GOOD = BasisCounts(
    listing_snapshot=date(2026, 10, 5),
    delisting_snapshot=date(2026, 10, 30),
    merged=True,
    listings=1000,
    no_id=10,
    stocks=1000,
    null_type=50,
    delisted=100,
    with_bars=98,
    unknown=5,
)  # fmt: skip  every share exactly at its threshold: met


def _gaps(counts: BasisCounts | None = GOOD, table: str = FORWARD_RETURNS_V3, grains=()) -> tuple:  # type: ignore[no-untyped-def,type-arg]
    return universe_basis(counts, LIMITS, table, grains).gaps


def test_every_share_at_its_threshold_is_free() -> None:
    found = universe_basis(GOOD, LIMITS, FORWARD_RETURNS_V3)
    assert (found.basis, found.gaps, found.counts) == (FREE, (), GOOD)


@pytest.mark.parametrize(
    ("change", "gap"),
    [
        ({"no_id": 11}, "listings_without_id"),
        ({"with_bars": 97}, "delisted_without_bars"),
        ({"unknown": 6}, "delisting_basis_unknown"),
        ({"null_type": 51}, "null_security_type"),
        ({"merged": False}, "listing_history_not_merged"),
    ],
)
def test_each_threshold_just_past_its_boundary_flips_exactly_one_gap(
    change: dict[str, object], gap: str
) -> None:
    found = universe_basis(replace(GOOD, **change), LIMITS, FORWARD_RETURNS_V3)  # type: ignore[arg-type]
    assert (found.basis, found.gaps) == (SURVIVORS, (gap,))


def test_a_threshold_moves_with_the_limits() -> None:
    loose = replace(LIMITS, max_no_id_share=0.02)
    worse = replace(GOOD, no_id=20)
    assert universe_basis(worse, loose, FORWARD_RETURNS_V3).basis == FREE
    assert universe_basis(worse, LIMITS, FORWARD_RETURNS_V3).gaps == ("listings_without_id",)


def test_the_v2_table_is_always_survivors_whatever_the_counts() -> None:
    found = universe_basis(GOOD, LIMITS, FORWARD_RETURNS)
    assert (found.basis, found.gaps) == (SURVIVORS, ("outcomes_not_v3",))


def test_a_grain_without_a_delisting_return_is_survivors() -> None:
    assert _gaps(grains=("share_path", "residual")) == ("grain_without_delisting_return",)


def test_no_counts_read_is_one_gap_beside_the_table_gap() -> None:
    assert _gaps(None, FORWARD_RETURNS) == ("listing_counts_unread", "outcomes_not_v3")


def test_nothing_to_count_a_share_of_is_a_gap_not_a_pass() -> None:
    assert _gaps(replace(GOOD, listings=0, no_id=0)) == ("no_listings_in_window",)
    assert _gaps(replace(GOOD, delisted=0, with_bars=0, unknown=0)) == ("no_delistings_in_window",)


def test_no_events_snapshot_is_its_own_gap_and_skips_the_delisting_shares() -> None:
    counts = replace(GOOD, delisting_snapshot=None, with_bars=0, unknown=100)
    assert _gaps(counts) == ("delisting_events_missing",)


def test_the_gaps_are_sorted_and_the_same_inputs_stamp_the_same_text() -> None:
    bad = replace(GOOD, no_id=500, unknown=90, null_type=900, merged=False)
    a = universe_basis(bad, LIMITS, FORWARD_RETURNS, ("chain", "share_path"))
    b = universe_basis(bad, LIMITS, FORWARD_RETURNS, ("share_path", "chain"))
    assert a == b and list(a.gaps) == sorted(a.gaps) and len(a.gaps) == 6
