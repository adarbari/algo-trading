"""Whether a learned screener beat its edge's rule screeners in the frozen period (ADR 0053
amendment, ED7c): the comparison behind promoting it by site config
(``[implementation] promoted``), over the stored rows of one run.

The comparison, per horizon the edge stores: the ``frozen`` slice rows of the run (not
exploratory, not in sample, role ``screener``, the edge's own ``main`` variant) of the model
screener and of every rule screener listed on the edge. The model wins a horizon when its lift
AND its decile spread are strictly greater than each rule screener's; a number not stored, a
missing row or no rule screener to beat is a failure, never a pass. It wins when it wins every
horizon. ML proposes and implements, never judges (decision 8): the judge is the frozen slice
of the harness, the same numbers that give any screener its status."""

from collections.abc import Sequence

from algotrade.config.edges.document import MAIN
from algotrade.services.read.evaluation.runs import EdgeRow
from algotrade.services.read.evaluation.track_record import FROZEN


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


def promotion_problems(
    rows: Sequence[EdgeRow], model: str, rules: Sequence[str], horizons: Sequence[int]
) -> list[str]:
    """Why ``model`` has not beaten ``rules`` in the frozen slice of ``rows`` (a run's stored
    rows) at every one of ``horizons``; empty when it has."""
    if not rules:
        return [f"{model}: the edge lists no rule screener to beat"]
    problems: list[str] = []
    for h in horizons:
        won = _frozen(rows, model, h)
        if won is None or won.lift is None or won.decile_spread is None:
            problems.append(f"{model} h={h}: no frozen lift and decile spread in the run")
            continue
        for rule in rules:
            lost = _frozen(rows, rule, h)
            if lost is None or lost.lift is None or lost.decile_spread is None:
                problems.append(f"{rule} h={h}: no frozen lift and decile spread in the run")
            elif not (won.lift > lost.lift and won.decile_spread > lost.decile_spread):
                problems.append(
                    f"{model} h={h}: lift {won.lift:.3f} / spread {won.decile_spread:.4f} do not "
                    f"both exceed {rule}'s {lost.lift:.3f} / {lost.decile_spread:.4f}"
                )
    return problems
