"""Whether a learned screener beat its edge's rule screeners in the frozen period (ADR 0053
amendment, ED7c): the one comparison behind promoting it by site config
(``[implementation] promoted``), over the stored rows of one run.

The comparison, at every horizon of the edge's outcome: the ``frozen`` slice rows of the run (not
exploratory, not in sample, role ``screener``, the edge's own ``main`` variant) of the promoted
model screener and of every rule screener the edge lists. Every compared row needs
``MIN_INDEPENDENT_SESSIONS`` sessions (the quality bar), and ``decile_sessions`` as many where
the spread is compared. The model wins a horizon when its lift AND its decile spread are strictly
greater than each rule screener's; a number not stored, a missing row, too few sessions or no rule
screener to beat is a failure, never a pass. It wins when it wins every horizon. ML proposes and
implements, never judges (decision 8): the judge is the frozen slice of the harness, the same
numbers that give any screener its status.

``load_promotion`` is the reader of ``promoted``: it honours it only when the comparison over the
cited run's stored rows is clean, else the edge is NOT promoted, with the reasons. The numbers the
document commits beside ``promoted`` (``Edge.compared``) are checked by the same function
(``committed_rows``)."""

from collections.abc import Sequence
from dataclasses import dataclass

from algotrade.config.edges import loading
from algotrade.config.edges.document import MAIN, MIN_INDEPENDENT_SESSIONS, Edge
from algotrade.config.strategy.schema import MODEL_IMPL
from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.configs import resolve_config
from algotrade.services.read.context import Stores
from algotrade.services.read.evaluation import edges as read_edges
from algotrade.services.read.evaluation import runs
from algotrade.services.read.evaluation.runs import EdgeRow
from algotrade.services.read.evaluation.track_record import FROZEN
from algotrade.storage.configs.store import ConfigStore


@dataclass(frozen=True)
class Promotion:
    """``promoted``: the screener the edge document names, or None when it names none or the
    comparison does not hold (``reasons``)."""

    edge_id: str
    promoted: str | None
    reasons: tuple[str, ...] = ()


def _frozen(rows: Sequence[EdgeRow], variant: str, horizon: int) -> EdgeRow | None:
    found = [
        r
        for r in rows
        if r.variant == variant
        and r.role == "screener"
        and r.edge_variant == MAIN
        and r.horizon_sessions == horizon
        and r.slice_kind == FROZEN
        and not r.exploratory
        and not r.in_sample
    ]
    return found[0] if len(found) == 1 else None


def _usable(row: EdgeRow | None) -> str | None:
    """Why ``row`` cannot be compared, else None."""
    if row is None:
        return "no frozen row in the run"
    if row.lift is None or row.decile_spread is None:
        return "no frozen lift and decile spread"
    for name, n in (("sessions", row.sessions), ("decile sessions", row.decile_sessions)):
        if n is None or n < MIN_INDEPENDENT_SESSIONS:
            return f"{n} {name}, under the {MIN_INDEPENDENT_SESSIONS} the quality bar asks"
    return None


def _ahead(won: EdgeRow, lost: EdgeRow) -> bool:
    """Lift and decile spread both strictly higher (rows ``_usable`` has cleared)."""
    assert won.lift is not None and won.decile_spread is not None
    assert lost.lift is not None and lost.decile_spread is not None
    return won.lift > lost.lift and won.decile_spread > lost.decile_spread


def promotion_problems(edge: Edge, rows: Sequence[EdgeRow], rules: Sequence[str]) -> list[str]:
    """Why ``edge.promoted`` has not beaten the rule screeners ``rules`` in the frozen slice of
    ``rows`` (a run's stored rows) at every horizon of the edge; empty when it has."""
    model = edge.promoted
    if model is None:
        return [f"{edge.id}: no promoted screener"]
    if not rules:
        return [f"{model}: the edge lists no rule screener to beat"]
    problems: list[str] = []
    for h in edge.outcome.horizon_sessions:
        won = _frozen(rows, model, h)
        if (why := _usable(won)) is not None:
            problems.append(f"{model} h={h}: {why}")
            continue
        assert won is not None and won.lift is not None and won.decile_spread is not None
        for rule in rules:
            lost = _frozen(rows, rule, h)
            if (why := _usable(lost)) is not None:
                problems.append(f"{rule} h={h}: {why}")
            elif lost is not None and not _ahead(won, lost):
                problems.append(
                    f"{model} h={h}: lift {won.lift:.3f} / spread {won.decile_spread:.4f} do not "
                    f"both exceed {rule}'s {lost.lift:.3f} / {lost.decile_spread:.4f}"
                )
    return problems


def rule_screeners(edge: Edge, configs: ConfigStore) -> list[str]:
    """The screeners the edge lists that are not the promoted one nor a model screener."""
    site = UserContext(SITE_USER)
    return [
        s
        for s in edge.screeners
        if s != edge.promoted and resolve_config(configs, s, site).config.impl != MODEL_IMPL
    ]


def committed_rows(edge: Edge) -> list[EdgeRow]:
    """The numbers the document commits (``[[implementation.compared]]``) as frozen-slice rows."""
    return [
        EdgeRow(
            edge_variant=MAIN, variant=c.screener, role="screener", horizon_sessions=c.horizon,
            slice_kind=FROZEN, slice_value=FROZEN, sessions=c.sessions, picks=None, hits=None,
            trials=None, pre_snapshot_sessions=None, hit_rate=None, base_rate=None, lift=c.lift,
            mean_excess_picks=None, decile_spread=c.decile_spread, decile_t=None,
            effect_size=None, sharpe=None, deflated_sharpe=None, pbo=None,
            decile_sessions=c.decile_sessions,
        )
        for c in edge.compared
    ]  # fmt: skip


def load_promotion(ctx: Stores, edge_id: str) -> Promotion:
    """``edge_id``'s promoted screener as the cited run's stored rows allow it."""
    edge = next(
        (e for e in loading.load_edges(ctx.configs, ctx.user.user_id) if e.id == edge_id), None
    )
    if edge is None or edge.promoted is None:
        return Promotion(edge_id, None)
    if edge.evidence is None or edge.status not in ("evidenced", "live"):
        return Promotion(
            edge_id, None, (f"{edge_id}: a promotion cites its run (evidenced, live)",)
        )
    summary = read_edges.load_edge(ctx, edge_id)
    candidates = runs.load_edge_runs(ctx, summary) if summary else ()
    run = next((r for r in candidates if r.run_id == edge.evidence.run_id), None)
    if run is None or run.exploratory:
        why = f"run {edge.evidence.run_id} is not a committed run at the frozen period"
        return Promotion(edge_id, None, (why,))
    problems = promotion_problems(
        edge, runs.load_run_rows(ctx, run), rule_screeners(edge, ctx.configs)
    )
    return Promotion(edge_id, None if problems else edge.promoted, tuple(problems))
