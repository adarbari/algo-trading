"""The variants a run measures and the scope each is valued in (ADR 0053, ADR 0088 G19): a
``Variant`` is one screener, baseline or grid member of the run; a position baseline
(``position:<template>``) is the setup's own picks valued as another template, so its scope is the
setup's with that template's outcome (``variant_scope``). Split from ``measuring.py`` at its line
cap."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from algotrade.config.edges.document import Edge
from algotrade.config.edges.portfolio import ENSEMBLE
from algotrade.config.edges.positions.chain import grain_name
from algotrade.config.edges.positions.templates import Templates
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.strategy.schema import Selection
from algotrade.services.evaluation.cross_section.baselines.outcome import position_outcome


@dataclass(frozen=True)
class Variant:
    """One screener or baseline of the run; the ``ensemble`` variant (ADR 0074) has the screeners
    of its pre-registered grid as ``members`` (their ``role`` is ``member``) and, as ``config``,
    the first one's (only its kind is read)."""

    id: str
    role: str  # "screener" | "baseline" | "member"
    config: ResolvedConfig
    members: tuple["Variant", ...] = ()
    position: str | None = None  # a baseline of the setup's own picks valued as this template

    @property
    def hash(self) -> str:
        """What the variant's trial is: its config's hash; an ensemble's is that of its grid (the
        members' hashes, in no order: an average does not depend on it)."""
        if self.position is not None:  # the screener's picks, another position: another trial key
            return hashlib.sha256(f"{self.id}:{self.config.hash}".encode()).hexdigest()
        if not self.members:
            return self.config.hash
        grid = json.dumps(sorted(m.config.hash for m in self.members))
        return hashlib.sha256(f"{ENSEMBLE}:{grid}".encode()).hexdigest()


@dataclass(frozen=True)
class _Scope:
    """One evaluation of the edge: ``main`` or one of its ``[[variants]]``."""

    key: str
    edge: Edge  # the edge with the variant's outcome and universe applied
    universe: Selection
    iv_field: str  # the outcome's own, else the run's
    overrides: tuple[str, ...] = ()  # the variant's base / picks overrides, in its trial key
    templates: Templates = field(default_factory=dict)  # the site's, for a position baseline


def variant_scope(scope: _Scope, variant: Variant) -> _Scope:
    """``scope`` as ``variant`` values it: a position baseline's picks are the setup's own, its
    outcome the template's (``baselines/outcome.py``) under a key of its own (the outcome caches
    are per scope key); any other variant is measured in the scope as it is."""
    if variant.position is None:
        return scope
    outcome = position_outcome(scope.edge.outcome, variant.position, scope.templates)
    return replace(
        scope, key=f"{scope.key}|{variant.id}", edge=replace(scope.edge, outcome=outcome)
    )


def grain_of(scope: _Scope) -> str:
    """The outcome grain the scope's outcome is read from (``data/outcomes/grains.py``): the
    option trades, the share paths of a shares position with an exit, or the price windows."""
    return grain_name(scope.edge.outcome)


def beside(plans: Sequence[Any], variants: Sequence[Variant]) -> str | None:
    """The other outcome grain a position baseline is valued on than its plan's (an option or
    share path setup against the stock alone): the run then reads both. None: every variant is on
    its plan's grain. A baseline is valued on the stock or the option grain only
    (``baselines/outcome.py``), so there is at most one."""
    other = {
        grain
        for p in plans
        for v in variants
        if v.position is not None
        and (grain := grain_of(variant_scope(p.scope, v))) != grain_of(p.scope)
    }
    return next(iter(other), None)
