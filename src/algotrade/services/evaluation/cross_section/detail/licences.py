"""The licence of a trial and of each per-name column of its ledger (ADR 0064 decision 10, ADR
0028): the most restrictive catalogue licence of what the trial reads. The trial's (on
``edge_eval`` and every ledger row) is that of its implied-vol field (when the outcome reads one),
its screen's features and its universe's features; a ledger column's is that of what it is
derived from: the outcome value (with its gross value, reference and touch) from the implied-vol
field, the score from the screen's features, the ADV from its own field. A field the catalogue
does not know (a reference field such as ``instrument.status``) is open. A reader redacts a
per-name value by the licence recorded here, never by a column's name."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

from algotrade.config.edges.document import Edge
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import Selection
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import strictest
from algotrade.services.evaluation.cross_section.reads.session import ADV_FIELD
from algotrade.services.selection import selection_fields

OPEN = "open"


@dataclass(frozen=True)
class TrialLicences:
    """``trial``: the trial's own; ``value``, ``score``, ``adv``: the ledger columns'; ``outcome``:
    the strictest licence of the outcome rows the run joined (ADR 0084 decision 1, ADR 0088
    decision 20): what gates the setup's verdict and picks, as the screen's and universe's
    fields keep their per-column redaction (decision B); it is part of ``trial``."""

    trial: str
    value: str
    score: str
    adv: str
    outcome: str = OPEN


def outcome_licence(rows: pd.DataFrame) -> str:
    """The strictest licence an outcome partition's rows record (a ``licence`` column; none, or a
    null in it, reads as open: ``forward_returns@v2`` has none). Per row, never by the table's
    name, so a share outcome over 2015 stays open and an option outcome priced from the bought
    history is personal (ADR 0084 decision 1)."""
    if "licence" not in rows.columns:
        return OPEN
    return strictest(str(x) for x in rows["licence"].dropna().unique())


def _of(features: FeatureSet, fields: Iterable[str]) -> str:
    found = (features.feature(f) for f in fields)
    return strictest(str(f.licence) for f in found if f is not None)


def screen_fields(config: ResolvedConfig, edge: Edge) -> tuple[str, ...]:
    """Every field a screener reads: its rules, its own selection and the edge's scorer."""
    fields = set(config.screen_spec.fields()) if config.config.rules else set()
    if config.selection is not None:
        fields.update(selection_fields(config.selection))
    fields.update(edge.scorer_features)
    return tuple(sorted(fields))


def trial_licences(
    features: FeatureSet,
    edge: Edge,
    universe: Selection,
    configs: Sequence[ResolvedConfig],
    iv_licence: str | None,
    outcome: str = OPEN,
) -> TrialLicences:
    """The licences of one trial (a screener or baseline of one edge variant; an ensemble's are
    those of every screener of its grid, the strictest); ``iv_licence``: its implied-vol field's
    (None: the outcome reads none); ``outcome``: that of the outcome rows joined."""
    score = strictest(_of(features, screen_fields(c, edge)) for c in configs)
    universe_licence = _of(features, selection_fields(universe))
    value = iv_licence or OPEN
    return TrialLicences(
        trial=strictest((value, score, universe_licence, outcome)),
        value=value,
        score=score,
        adv=_of(features, (ADV_FIELD,)),
        outcome=outcome,
    )


def picks_licence(
    features: FeatureSet,
    edge: Edge,
    universe: Selection,
    config: ResolvedConfig,
    iv_licence: str | None,
) -> str:
    """The strictest licence of what a paper pick of ``edge`` through ``config`` is read from
    (the trial's own: ``trial_licences``), recorded on each paper row at the signal."""
    return trial_licences(features, edge, universe, [config], iv_licence).trial
