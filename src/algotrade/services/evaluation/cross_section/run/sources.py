"""The price-source slices of one edge evaluation (ADR 0088 decision 11): the open verdict reads a
trial over Cboe rows only, so an edge that reads option trade rows is evaluated as up to two runs,
the open slice from ``FIRST_CBOE_CHAIN_SESSION`` and the history slice before it (bought
``option_history`` rows, a separate owner-only trial under its own run job). An edge that reads no
option rows is one unsplit slice. Straddling decisions (a decision session before the cutover whose
entry session is after it) go to the history slice."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.document import Edge
from algotrade.config.edges.positions.chain import OPTION_HISTORY, reads_chain
from algotrade.config.edges.positions.templates import Templates
from algotrade.core.model.errors import AlgoTradeError
from algotrade.core.time.calendar import previous_session
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION
from algotrade.services.evaluation.cross_section.run.evaluation import EdgeEvaluation

ALL = "all"  # an edge that reads no option rows: one run over the whole range
CBOE = "cboe"  # the open slice: decision sessions from the cutover, Cboe rows only
OPEN = "open"  # the licence of a row anyone may be served


@dataclass(frozen=True)
class SourceSlice:
    """One run of an evaluation: its price ``source`` and decision sessions ``start..end``."""

    source: str
    start: date
    end: date

    @property
    def job_suffix(self) -> str:
        """The run-record job suffix: the history run is its own trial log (``:option_history``),
        the open and the unsplit run share the edge's one."""
        return OPTION_HISTORY if self.source == OPTION_HISTORY else ""


def source_slices(
    edge: Edge, templates: Templates, start: date, end: date
) -> tuple[SourceSlice, ...]:
    """The runs of ``edge`` over ``start..end``, the open one first; empty slices are dropped."""
    if not reads_chain(edge, templates):
        return (SourceSlice(ALL, start, end),)
    history_end = min(end, previous_session(FIRST_CBOE_CHAIN_SESSION))
    found = (
        SourceSlice(CBOE, max(start, FIRST_CBOE_CHAIN_SESSION), end),
        SourceSlice(OPTION_HISTORY, start, history_end),
    )
    return tuple(s for s in found if s.start <= s.end)


def check_open(evaluation: EdgeEvaluation, source: SourceSlice) -> None:
    """Raise before publishing when an open slice's result joined a licensed outcome row: the open
    verdict must stay readable by every viewer (decision 11)."""
    if source.source != CBOE:
        return
    bad = sorted(
        {
            r.variant
            for r in evaluation.results
            if r.licences is not None and r.licences.outcome != OPEN
        }
    )
    if bad:
        raise AlgoTradeError(
            f"edge {evaluation.edge_id}: the open slice joined non-open outcome rows for {bad}; "
            f"it must read Cboe rows only (ADR 0088 decision 11)"
        )
