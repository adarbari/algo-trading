"""The user's train / test split (``EvaluationSplit``): their ``split_from`` from
``config/users/<id>/evaluation.toml`` (None: each edge's own ``frozen_from`` is the split), the
site frozen periods of the edges they see, and the latest stored session (the last date a split
may name). Configs, not session data: nothing is read from a table."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.edges.evaluation import load_evaluation
from algotrade.services.read.context import ReadContext
from algotrade.services.read.evaluation.edges import load_edges


@dataclass(frozen=True)
class FrozenPeriod:
    """One edge's frozen period: the first session of its test slice."""

    edge_id: str
    frozen_from: date


@dataclass(frozen=True)
class EvaluationSplit:
    """``split_from``: the user's own split (None: none set); ``frozen_periods``: the edges
    that have one, by id; ``latest_session``: the latest stored session."""

    split_from: date | None
    frozen_periods: tuple[FrozenPeriod, ...]
    latest_session: date


def load_evaluation_split(ctx: ReadContext) -> EvaluationSplit:
    """``ctx.user``'s split with the frozen periods of the edges they see; the latest session
    is the request's."""
    settings = load_evaluation(ctx.configs, ctx.user.user_id)
    periods = tuple(
        FrozenPeriod(e.id, e.frozen_from) for e in load_edges(ctx) if e.frozen_from is not None
    )
    return EvaluationSplit(settings.split_from, periods, ctx.session.date)
