"""Where a rule that reads a fitted score may be judged (ADR 0088 E14, risk 24; ADR 0053: a model
proposes, the harness judges).

A fitted score ``edge_score_<edge>`` is an expression feature whose description records
``fitted_through`` (the latest training window close) and the fit's ``horizon``. A setup whose
rules read one, directly or inside another expression, is judged only on decision sessions after
``fitted_through`` plus that horizon; earlier sessions are an ``in_sample`` slice the verdict
never reads. ``scored`` finds the scores a set of fields depends on, ``first_judged_session`` is
the first session judged, ``scored_identity`` is what a refit changes in a trial's identity."""

import re
from collections.abc import Iterable
from datetime import date

from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import next_session
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import Feature

PREFIX = "edge_score_"  # a learned scorer's feature name (render.py's)
FITTED = re.compile(r"fitted_through=(\d{4}-\d{2}-\d{2})")
HORIZON = re.compile(r"horizon=(\d+) sessions")


def fit_record(description: str) -> tuple[date, int] | None:
    """``(fitted_through, horizon)`` from a scorer's description (None: either is missing)."""
    fitted, horizon = FITTED.search(description), HORIZON.search(description)
    if fitted is None or horizon is None:
        return None
    return date.fromisoformat(fitted.group(1)), int(horizon.group(1))


def scored(features: FeatureSet, fields: Iterable[str]) -> tuple[Feature, ...]:
    """The fitted scores ``fields`` depend on, by name: a field named ``feature.edge_score_*`` and
    any expression feature whose formula reads one (the dependency closure, never a name prefix)."""
    found: dict[str, Feature] = {}
    for field in fields:
        name = field.removeprefix("feature.")
        if name not in features.expressions:
            continue
        for dep in features.plan([name], compute=[name])[1]:
            if dep.startswith(PREFIX):
                found[dep] = features.expressions[dep].feature
    return tuple(found[k] for k in sorted(found))


def first_judged_session(scores: Iterable[Feature]) -> date | None:
    """The first decision session a rule over ``scores`` may be judged on: the session after
    ``fitted_through`` plus the fit's horizon in sessions, the latest over the scores (None: no
    scores). A score whose description does not record its fit is refused: it fails closed."""
    latest: date | None = None
    for score in scores:
        record = fit_record(score.description)
        if record is None:
            raise ConfigurationError(
                f"{score.name}: the description records no fitted_through and horizon"
            )
        through, horizon = record
        day = through
        for _ in range(horizon + 1):
            day = next_session(day)
        latest = day if latest is None else max(latest, day)
    return latest


def scored_identity(scores: Iterable[Feature]) -> list[str]:
    """What a refit changes: each score's name, version and fit date, for the trial's identity (a
    refit is a new feature version, so another trial)."""
    return [f"{s.name}@v{s.version}:{(fit_record(s.description) or ('', 0))[0]}" for s in scores]
