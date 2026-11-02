"""The typed result of one edge evaluation (ADR 0053, ADR 0064): each trial's or comparison's
measures (``VariantResult``) with its measured legs (``LegDetail``), the random-pick backtests
matched to a screener (``RandomPicks``) and the run as a whole (``EdgeEvaluation``)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from algotrade.config.edges.document import MAIN
from algotrade.config.edges.identity import LONG
from algotrade.services.evaluation.cross_section.detail.licences import TrialLicences
from algotrade.services.evaluation.cross_section.detail.windows import SeriesFacts, counts_wins
from algotrade.services.evaluation.cross_section.historical import HistoricalCaveat
from algotrade.services.evaluation.cross_section.legs.reuse import FULL
from algotrade.services.evaluation.cross_section.measures import SessionStat, SliceMeasure
from algotrade.services.evaluation.cross_section.random_picks import RANDOM
from algotrade.services.evaluation.cross_section.reporting.report_containment import (
    ReportContainment,
)


@dataclass(frozen=True)
class LegDetail:
    """One leg of a measured block (leg v2, ADR 0064): its decision session D and entry session
    S, the block's measured first session (the side of the split it is on, as for the slices)
    and its statistic with every pick. What the ledger is framed from."""

    decision: date
    entry: date
    block: date
    stat: SessionStat


@dataclass(frozen=True)
class VariantResult:
    variant: str
    role: str
    config_hash: str
    horizon: int
    stats: tuple[SessionStat, ...]
    measures: tuple[SliceMeasure, ...]
    edge_variant: str = MAIN  # the edge's own ``[[variants]]`` id, "main" for the edge itself
    iv_source: str | None = None  # the run's iv_field when the outcome reads an implied vol
    licences: TrialLicences | None = None  # the trial's and its ledger columns' (ADR 0064)
    legs: tuple[LegDetail, ...] = ()  # the main edge variant's measured legs, for the ledger
    side: str = LONG  # the outcome's side (``edge_eval.side``; ADR 0053 amendment)
    capital_basis: str | None = None  # the trade contract's (ADR 0088); None for a book
    timing: Mapping[str, Any] | None = None  # a time-series edge: timing vs buy-and-hold Sharpe
    book: Mapping[str, Any] | None = None  # a named option sleeve's book and index tracking (E8b)
    grid: int | None = None  # an ensemble: the size of its pre-registered grid (ADR 0074)

    @property
    def licence(self) -> str | None:
        """The trial's: the strictest of its implied-vol field, screen and universe features."""
        return None if self.licences is None else self.licences.trial

    @property
    def unit(self) -> str | None:
        """What the values measure (``series.unit``); None when no series was built."""
        return None if self.series is None else self.series.unit

    @property
    def wins(self) -> bool:
        """The trial statistics read the excess wins: the values are not returns."""
        return counts_wins(self.unit)

    lost_sessions: Mapping[str, int] = field(default_factory=dict)  # table -> decision sessions
    report_containment: ReportContainment | None = None  # earnings_expected edges: diagnostic
    series: SeriesFacts | None = None  # the windows of ``stats``, the unit, the projection (0064)
    costs: tuple[SliceMeasure, ...] = ()  # cost rows of a return outcome (ADR 0064 decision 5)


@dataclass(frozen=True)
class RandomPicks:
    """The random-pick backtest matched to one screener of one edge variant at one horizon:
    one measure per draw over the out-of-sample slice (``random_picks.py``)."""

    edge_variant: str
    horizon: int
    variant: str  # the screener the draws are matched to
    config_hash: str  # that screener's trial hash
    draws: tuple[SliceMeasure, ...]
    kind: str = RANDOM  # ``RANDOM`` (uniform) or ``SECTOR_RANDOM`` (matched to the picks' sectors)
    side: str = LONG


@dataclass(frozen=True)
class EdgeEvaluation:
    edge_id: str
    run_hash: str
    user_id: str
    benchmark: str  # the edge document's: "SPY" or "none"
    start: date
    end: date
    as_of: datetime
    snapshot: date | None  # the first (here: earliest read) universe snapshot
    results: tuple[VariantResult, ...]
    trials: int
    start_sessions: Mapping[int, int]  # horizon -> decision blocks the schedule gave
    unclosed_sessions: Mapping[int, int]  # horizon -> of those, blocks with no closed window
    event_unknown: Mapping[str, int] = field(default_factory=dict)  # reason -> names excluded
    split_from: date | None = None  # the test slice's first session (None: no split)
    exploratory: bool = False  # the split is not the edge's frozen_from: never evidence
    # Sessions before the first reference snapshot, read from the listing history (ADR 0053
    # amendment 2026-10-09): the rule and the names by path; None when none was read.
    historical: HistoricalCaveat | None = None
    random_picks: tuple[RandomPicks, ...] = ()  # out-of-sample only: none without a split
    # The run's legs, the reads of its sessions and its outcome reads as ``results/edge_legs``
    # rows (``legs/rows.py``): what ``write_edge_eval`` stores with the run (ADR 0063).
    leg_rows: tuple[Mapping[str, Any], ...] = field(default=(), repr=False, compare=False)
    # How the run got its legs (ADR 0063): ``full`` or ``incremental``, the stored legs it
    # reused, the ones it computed and the stored ones it recomputed, by reason.
    mode: str = FULL
    legs_reused: int = 0
    legs_computed: int = 0
    legs_invalidated: Mapping[str, int] = field(default_factory=dict)
    # The share of an in-sample Sharpe ratio to expect lost out of sample (``verdict.toml
    # [oos_haircut]`` of the edge's ``oos_class``; None: the edge has none), for the report.
    oos_haircut: float | None = None
    # Each screener's config hash as the run resolved it (``Variant.hash``), recorded in the run
    # record's stats so the provenance line can tell a screener changed since (empty: none).
    screener_hashes: Mapping[str, str] = field(default_factory=dict)
    # The bootstrap's draws, mean block and seed version, recorded in the run record's stats
    # (the evidence measures' audit, ADR 0088 2.6); empty: no tail measures (a time-series run).
    bootstrap: Mapping[str, Any] = field(default_factory=dict)
    # The main outcome's declared exits (``spec.exits_digest``; None: no position), in the stats.
    exits_digest: str | None = None
