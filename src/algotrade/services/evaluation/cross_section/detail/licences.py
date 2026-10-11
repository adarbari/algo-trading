"""The licence of a trial and of each per-name column of its ledger (ADR 0064 decision 10, ADR
0028): the most restrictive catalogue licence of what the trial reads. The trial's (on
``edge_eval`` and every ledger row) is that of its implied-vol field (when the outcome reads one),
its screen's features and its universe's features; a ledger column's is that of what it is
derived from: the outcome value (with its gross value, reference and touch) from the implied-vol
field, the score from the screen's features, the ADV from its own field. A field the catalogue
does not know (a reference field such as ``instrument.status``) is open. A reader redacts a
per-name value by the licence recorded here, never by a column's name."""

from collections.abc import Iterable
from dataclasses import dataclass

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
    """``trial``: the trial's own; ``value``, ``score``, ``adv``: the ledger columns'."""

    trial: str
    value: str
    score: str
    adv: str


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
    config: ResolvedConfig,
    iv_licence: str | None,
) -> TrialLicences:
    """The licences of one trial (a screener or baseline of one edge variant); ``iv_licence``:
    its implied-vol field's (None: the outcome reads none)."""
    score = _of(features, screen_fields(config, edge))
    universe_licence = _of(features, selection_fields(universe))
    value = iv_licence or OPEN
    return TrialLicences(
        trial=strictest((value, score, universe_licence)),
        value=value,
        score=score,
        adv=_of(features, (ADV_FIELD,)),
    )
