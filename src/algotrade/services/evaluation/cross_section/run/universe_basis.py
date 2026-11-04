"""The run stamp ``universe_basis`` (ADR 0087 decision 6): whether the window an evaluation read
was free of survivorship, so a verdict knows what it was measured on.

``universe_basis`` is a pure predicate over the counts the data layer returned
(``data.listings.basis.universe_basis_counts``), the thresholds of ``verdict.toml
[universe_basis]``, the outcomes table the run read and the outcome grains it measured. The stamp
is ``free`` only when no gap is found; otherwise ``survivors``, with every gap named (sorted, so
the same inputs stamp the same text). The verdict rule reads the stamp only, never the zero
figure or a count.

Gaps (a share compared with its threshold counts as met at equality):

- ``listing_counts_unread``: no listing history or membership snapshot to count (a run that did
  not read the universe, or a store without them);
- ``listing_history_not_merged``: the snapshot is not the merged one (no ``id_source``);
- ``no_listings_in_window`` / ``no_delistings_in_window``: nothing to count a share of;
- ``listings_without_id``: the share of qualifying listings with no id is above the limit;
- ``delisted_without_bars``: the share of the window's delisted names with bars to their last
  bar is below the limit;
- ``delisting_events_missing``: no delisting-events snapshot stored by the run's ``as_of``;
- ``delisting_basis_unknown``: the share of the delisted with an unknown delisting return
  (``ZERO_UNKNOWN`` or no event row) is above the limit;
- ``outcomes_not_v3``: the run read an outcomes table other than ``forward_returns@v3`` (always,
  while ``data.outcomes.reading.READ_TABLE`` is v2: today every stamp is ``survivors``);
- ``null_security_type``: the share of stock listings with no ``security_type`` is above the limit;
- ``grain_without_delisting_return``: the run measured a share path, residual or option-chain
  outcome, whose grain carries no delisting return yet (PR6d)."""

from collections.abc import Collection
from dataclasses import dataclass

from algotrade.config.edges.document import Edge
from algotrade.config.edges.positions.chain import CHAIN_KIND, reads_share_path
from algotrade.config.edges.universe_basis import UniverseBasisLimits
from algotrade.data.listings.basis import BasisCounts
from algotrade.services.evaluation.cross_section.hit import needs_residual
from algotrade.storage.tables.schemas import FORWARD_RETURNS_V3

SURVIVORS, FREE = "survivors", "free"
RESIDUAL = "residual"
EPSILON = 1e-12  # a share at its threshold is met (counts are integers, thresholds decimals)


@dataclass(frozen=True)
class UniverseBasis:
    """The stamp, its sorted gaps and the counts it was decided on (None: none were read)."""

    basis: str
    gaps: tuple[str, ...]
    counts: BasisCounts | None = None
    limits: UniverseBasisLimits | None = None  # the thresholds it was decided against


def grains_without_delisting_return(edges: Collection[Edge]) -> tuple[str, ...]:
    """The grains among ``edges``' outcomes that carry no delisting return: ``share_path``,
    ``residual`` and ``chain`` (sorted, deduplicated; the price-window grain is not one)."""
    found: set[str] = set()
    for edge in edges:
        o = edge.outcome
        if o.kind == CHAIN_KIND:
            found.add("chain")
        elif reads_share_path(o):
            found.add("share_path")
        if needs_residual(edge):
            found.add(RESIDUAL)
    return tuple(sorted(found))


def _share(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _count_gaps(counts: BasisCounts, limits: UniverseBasisLimits) -> set[str]:
    """The gaps found in ``counts`` against ``limits`` (see the module docstring)."""
    gaps: set[str] = set()
    if not counts.merged:
        gaps.add("listing_history_not_merged")
    if not counts.listings:
        gaps.add("no_listings_in_window")
    elif _share(counts.no_id, counts.listings) > limits.max_no_id_share + EPSILON:
        gaps.add("listings_without_id")
    if counts.stocks and _share(counts.null_type, counts.stocks) > (
        limits.max_null_type_share + EPSILON
    ):
        gaps.add("null_security_type")
    if counts.delisting_snapshot is None:
        gaps.add("delisting_events_missing")
    if not counts.delisted:
        gaps.add("no_delistings_in_window")
        return gaps
    if counts.delisting_snapshot is not None:
        if _share(counts.with_bars, counts.delisted) < limits.min_delisted_bars_share - EPSILON:
            gaps.add("delisted_without_bars")
        if _share(counts.unknown, counts.delisted) > limits.max_unknown_delisting_share + EPSILON:
            gaps.add("delisting_basis_unknown")
    return gaps


def universe_basis(
    counts: BasisCounts | None,
    limits: UniverseBasisLimits,
    read_table: str,
    grains: Collection[str] = (),
) -> UniverseBasis:
    """The stamp of a run: ``free`` only with no gap. ``counts``: None when the listing history was
    not read; ``read_table``: the outcomes table the run read (``READ_TABLE``); ``grains``: the
    grains without a delisting return it measured (``grains_without_delisting_return``)."""
    gaps: set[str] = set() if counts is None else _count_gaps(counts, limits)
    if counts is None:
        gaps.add("listing_counts_unread")
    if read_table != FORWARD_RETURNS_V3:
        gaps.add("outcomes_not_v3")
    if grains:
        gaps.add("grain_without_delisting_return")
    return UniverseBasis(SURVIVORS if gaps else FREE, tuple(sorted(gaps)), counts, limits)
