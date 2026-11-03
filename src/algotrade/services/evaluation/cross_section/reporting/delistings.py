"""The delistings of an edge evaluation (ADR 0087 decision 5): what the window's delisted names
were (counts by delisting reason and by the basis of their delisting return, from the
the delisting-events snapshot the stamp was decided on) and what the delisting return did to the
screeners' picks: per screener and horizon of the main edge variant, the counted picks that were
delisted by basis and the headline beside the zero-convention figure (the same picks with the
delisting return taken out, so the report never hides what the convention contributes). The
``universe_basis`` stamp itself is decided in ``run/universe_basis.py``; the verdict reads it,
never these figures."""

from collections import Counter
from typing import Any

from algotrade.services.evaluation.cross_section.measures import SCREENER
from algotrade.services.evaluation.cross_section.run.evaluation import EdgeEvaluation


def _picks_of(evaluation: EdgeEvaluation) -> list[dict[str, Any]]:
    """Per screener and horizon with measured legs: the counted picks, their hits, the hits and
    mean value with the delisting return taken out, and the delisted picks by basis (a pick with no
    stored basis, a v2 outcome row, counts as ``none``)."""
    found = []
    for r in evaluation.results:
        if r.role != SCREENER or not r.legs:
            continue
        counted = [p for leg in r.legs for p in leg.stat.picks if p.reason == ""]
        # a pick that was not delisted reads the same with the return taken out: its own figures
        zero = [
            (
                p.value if p.zero_value is None else p.zero_value,
                p.zero_hit if p.zero_value is not None else p.hit,
            )
            for p in counted
        ]
        values = [p.value for p in counted if p.value is not None]
        zeros = [v for v, _ in zero if v is not None]
        found.append(
            {
                "variant": r.variant,
                "horizon": r.horizon,
                "picks": len(counted),
                "hits": sum(p.hit for p in counted),
                "zero_picks": len(zero),
                "zero_hits": sum(bool(h) for _, h in zero),
                "mean_value": sum(values) / len(values) if values else None,
                "mean_zero_value": sum(zeros) / len(zeros) if zeros else None,
                "delisted_by_basis": dict(
                    sorted(
                        Counter(p.delisting_basis or "none" for p in counted if p.delisted).items()
                    )
                ),
            }
        )
    return found


def delistings(evaluation: EdgeEvaluation) -> dict[str, Any]:
    """The run's ``stats["delistings"]``: the window's delisted names (None counts when the
    listing history was not read) and the picks' figures (see the module docstring)."""
    stamp = evaluation.universe_basis
    counts = None if stamp is None else stamp.counts
    window = (
        None
        if counts is None
        else {
            "delisted": counts.delisted,
            "with_bars": counts.with_bars,
            "unknown": counts.unknown,
            "snapshot": None
            if counts.delisting_snapshot is None
            else counts.delisting_snapshot.isoformat(),
            "by_reason": dict(counts.by_reason),
            "by_basis": dict(counts.by_basis),
        }
    )
    return {"window": window, "picks": _picks_of(evaluation)}
