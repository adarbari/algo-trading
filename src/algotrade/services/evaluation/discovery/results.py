"""The typed result of one discovery run: what the winners study's job persists and the drafts
writer reads (ADR 0053 amendment 2026-10-09). Frozen records only; no computation."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.winners import WinnersStudySettings

PROPOSED_BY = "model"  # the proposer's rows carry this and no verdict (ML proposes, never judges)


@dataclass(frozen=True)
class SessionSummary:
    """One grid session: ``eligible`` names, ``winners`` (excess return at or above ``threshold``
    among the eligible with a COMPLETE or DELISTED outcome), the controls ``wanted`` and
    ``drawn`` (fewer when a cell ran out of names), the share of eligible names with no outcome
    row (``missing_fraction``) and the ``block`` of non-overlapping horizons it belongs to."""

    session: date
    block: int
    eligible: int
    winners: int
    controls_wanted: int
    controls_drawn: int
    threshold: float
    missing_fraction: float


@dataclass(frozen=True)
class Exclusion:
    """A feature left out of the discovery at ``sessions`` grid sessions, and why."""

    feature: str
    reason: str
    sessions: int


@dataclass(frozen=True)
class Effect:
    """One feature at one grid session: Hedges' g of winners over controls (``None`` when
    undefined), the share of each group with a stored value, the rows that had one, and whether
    it ``counted`` (both coverages at least the minimum and within the allowed gap) with the
    ``reason`` when not. UNKNOWN values are dropped and counted, never imputed."""

    feature: str
    session: date
    g: float | None
    winners: int
    controls: int
    coverage_winners: float
    coverage_controls: float
    counted: bool
    reason: str


@dataclass(frozen=True)
class BlockEffect:
    """A feature's mean effect over the counted grid sessions of one block."""

    feature: str
    block: int
    mean_g: float
    sessions: int


@dataclass(frozen=True)
class Tell:
    """A feature pooled over blocks: the mean of its block effects, the sign most blocks share,
    how many blocks agree, whether both halves agree, ``stable`` and ``qualifies`` (stable and
    |mean| above the gate); ``cluster`` the index into ``DiscoveryResult.clusters`` of a
    qualifying tell."""

    feature: str
    mean_g: float
    blocks: int
    sign: int
    agreeing_blocks: int
    halves_agree: bool
    stable: bool
    qualifies: bool
    cluster: int | None


@dataclass(frozen=True)
class Proposal:
    """The ML proposer's ranking of a feature (``rank`` 1 is best). No verdict: the gate judges."""

    feature: str
    rank: int
    coefficient: float
    gain: float
    rows: int
    converged: bool
    proposed_by: str = PROPOSED_BY


@dataclass(frozen=True)
class DiscoveryResult:
    """One run: its ``settings`` and the controls' ``seed``, the grid ``sessions``, every
    ``effect`` per (feature, session), the ``block_effects`` and pooled ``tells``, the
    ``clusters`` of qualifying tells (feature names), what was ``excluded``, the gate
    (``observed_clusters`` against the ``null_counts`` of the permutations, ``passed``), the
    number of ``blocks`` and the ``proposals``. A block is ``block_sessions`` sessions of grid
    sessions; blocks are not strictly independent: the windows of one block's last sessions
    overlap the next block's, so report "blocks", never "independent sessions"."""

    settings: WinnersStudySettings
    seed: int
    sessions: tuple[SessionSummary, ...]
    effects: tuple[Effect, ...]
    block_effects: tuple[BlockEffect, ...]
    tells: tuple[Tell, ...]
    clusters: tuple[tuple[str, ...], ...]
    excluded: tuple[Exclusion, ...]
    observed_clusters: int
    null_counts: tuple[int, ...]
    null_threshold: float
    passed: bool
    blocks: int  # not strictly independent: neighbouring blocks' windows overlap
    proposals: tuple[Proposal, ...]
