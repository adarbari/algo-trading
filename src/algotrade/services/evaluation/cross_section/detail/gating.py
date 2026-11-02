"""What a setup gate does to a variant's measured blocks (ADR 0088, design 2.2): each session is
tagged with the gate's state at D (open / closed / unknown); the slices read every block, the
edge's own series, ledger and random draws only the open ones. An ungated edge passes through
unchanged."""

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace
from datetime import date

from algotrade.config.edges.document import Edge
from algotrade.engines.screening.gate import OPEN
from algotrade.services.configs import field_catalog
from algotrade.services.evaluation.cross_section.measures import SessionStat, pool_stats
from algotrade.services.evaluation.cross_section.reads.session import SessionReads
from algotrade.services.evaluation.cross_section.sessions import Leg
from algotrade.storage.configs.store import ConfigStore


def tagged(
    found: Mapping[date, SessionStat], edge: Edge, session: SessionReads
) -> Mapping[date, SessionStat]:
    """``found`` with each session tagged by the setup gate's state at D (none: unchanged)."""
    if edge.gate is None:
        return found
    return {d: replace(s, gate=session.gate(edge.gate, d)) for d, s in found.items()}


def open_blocks(
    edge: Edge, blocks: Sequence[Sequence[Leg]], found: Mapping[date, SessionStat]
) -> list[Sequence[Leg]]:
    """``blocks`` of a gated edge whose first decision session's gate is open (the edge's own
    result: the random draws, the series and the ledger read these; the slices read them all);
    every block of an ungated edge."""
    if edge.gate is None:
        return list(blocks)
    return [b for b in blocks if (s := found.get(b[0].decision)) is not None and s.gate == OPEN]


def pooled_blocks(
    edge: Edge,
    found: Mapping[date, SessionStat],
    kept: Sequence[Sequence[Leg]],
    closed: Collection[date],
) -> tuple[tuple[SessionStat, ...], list[Sequence[Leg]], tuple[SessionStat, ...]]:
    """The measured blocks' pooled statistics: every one (the slices read all of them), and the
    open blocks with their statistics (the edge's own series, ledger and draws)."""
    every = tuple(
        pool_stats(
            [found[leg.decision] for leg in block if leg.entry in closed and leg.decision in found]
        )
        for block in kept
    )
    return (every, *open_only(edge, kept, every))


def open_only(
    edge: Edge, kept: Sequence[Sequence[Leg]], every: tuple[SessionStat, ...]
) -> tuple[list[Sequence[Leg]], tuple[SessionStat, ...]]:
    """The measured blocks of a gated edge and their pooled statistics, the open ones only."""
    if edge.gate is None:
        return list(kept), every
    pairs = [(b, s) for b, s in zip(kept, every, strict=True) if s.gate == OPEN]
    return [b for b, _ in pairs], tuple(s for _, s in pairs)


def gate_domains(configs: ConfigStore, edge: Edge) -> dict[str, tuple[str, ...]] | None:
    """The catalogue's string domains, read only for a gated edge: a label the gate never saw is
    read as missing (UNKNOWN), never open."""
    return None if edge.gate is None else dict(field_catalog(configs).domains)


type Series = tuple[SessionStat, ...]


def turned(every: Series, own: Series, turn: Callable[[Series], Series]) -> tuple[Series, Series]:
    """``every`` and ``own`` (its open part) through ``turn`` (the turnover cost of a band or a
    book); an ungated edge, whose two are the one series, turns it once."""
    turned_own = turn(own)
    return (turned_own if own == every else turn(every)), turned_own
