"""B1 formulas of a screen draft (ADR 0041, amended 2026-10-11): a concept the catalogue lacks
that is a same-session expression over existing features. The model proposes each as
``{name, expr, dtype, unit, description, null_meaning, inputs, criterion}``; this module
decides what the server offers the trader, never the model:

- the shape, the ``draft_`` name (no site or own feature shadowed, no repeat) and the formula,
  type-checked as a user feature (``FeatureSet.with_user``, as ``services.authoring``
  does), whose ``inputs`` must be exactly the names it reads;
- the fingerprint (``features.expressions.fingerprint``): a formula equal to a site feature or
  the trader's own is dropped and its criterion rewritten onto that field (the caller places
  it); an invalid one is dropped with the reason (``formulas_dropped``);
- a dry run on the request's session (``services.preview.dry_run``: no-value rate, range, how
  many rows pass the criterion, a few samples) so the trader sees what accepting it does.

A kept formula is *pending*: nothing is saved or put in the draft document; the formula and its
criterion travel together until the trader accepts (the UI saves it as their own feature).
Reads the catalogue and the session; writes nothing."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.features.expressions.fingerprint import find_duplicate, fingerprint
from algotrade.features.expressions.nodes import ExpressionError
from algotrade.services.drafting.answer_schema import FORMULA, check_item
from algotrade.services.preview.expressions import DryRun, dry_run
from algotrade.services.read.context import ReadContext

PREFIX = "draft_"
THEME = "draft"
_NAME = re.compile(r"^draft_[a-z][a-z0-9_]{0,55}$")
_SYMBOL = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "==", "ne": "!="}

# What turns a raw criterion item and its field into the draft's criterion table entry
# (``screens._criterion``: raises ``ConfigurationError``).
Normalise = Callable[[Mapping[str, Any], str], dict[str, Any]]


@dataclass(frozen=True)
class DraftFormula:
    """A formula that checked and was dry-run: pending until the trader accepts it."""

    name: str
    expr: str
    dtype: str
    unit: str
    description: str
    null_meaning: str
    inputs: tuple[str, ...]
    criterion: dict[str, Any] | None  # the criterion on ``feature.<name>``, pending with it
    fingerprint: str
    dry_run: DryRun
    pending: bool = True  # never saved or in the document until the trader accepts it


@dataclass(frozen=True)
class DroppedFormula:
    """A formula the draft does not offer, and why. ``existing``: the feature it duplicates
    (its criterion then uses that field instead)."""

    name: str
    reason: str
    existing: str | None = None


@dataclass(frozen=True)
class FormulaOutcome:
    formulas: tuple[DraftFormula, ...]
    dropped: tuple[DroppedFormula, ...]
    rewritten: Mapping[str, dict[str, Any]]  # duplicate's name -> its criterion on the field
    notes: tuple[str, ...]


def check_formulas(
    ctx: ReadContext, proposal: Mapping[str, Any], normalise: Normalise
) -> FormulaOutcome:
    """Every proposed formula of ``proposal`` validated for ``ctx``'s user, as above."""
    raw = proposal.get("formulas")
    items = raw if isinstance(raw, list) else []
    kept: list[DraftFormula] = []
    dropped: list[DroppedFormula] = []
    rewritten: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    seen: set[str] = set()
    for n, item in enumerate(items, 1):
        name = _name_of(item, n)
        try:
            if (shape := check_item(item, FORMULA, "formula")) is not None:
                raise ConfigurationError(f"not the formula shape ({shape})")
            if name in seen:
                raise ConfigurationError("the name is used by another proposed formula")
            seen.add(name)
            result = _check(ctx, item, normalise)
        except ConfigurationError as exc:
            dropped.append(DroppedFormula(name, getattr(exc, "message", None) or str(exc)))
            continue
        if isinstance(result, DraftFormula):
            kept.append(result)
            continue
        existing, criterion = result
        reason = f"the same formula as the existing feature {existing}"
        dropped.append(DroppedFormula(name, reason, existing))
        notes.append(f"{name} is {existing}: its criterion uses that field")
        if criterion is not None:
            rewritten[name] = criterion
    return FormulaOutcome(tuple(kept), tuple(dropped), rewritten, tuple(notes))


def _name_of(item: Any, n: int) -> str:
    name = item.get("name") if isinstance(item, Mapping) else None
    return name if isinstance(name, str) and name else f"formula_{n}"


def _check(
    ctx: ReadContext, item: Mapping[str, Any], normalise: Normalise
) -> DraftFormula | tuple[str, dict[str, Any] | None]:
    name = item["name"]
    if not _NAME.match(name):
        raise ConfigurationError(
            f"the name must be {PREFIX} followed by a-z, 0-9 and _ (at most 61 characters)"
        )
    if ctx.features.feature(name) is not None:
        raise ConfigurationError(f"{name} is already a feature of this catalogue")
    definition = FeatureDefinition(
        name=name,
        theme=THEME,
        expr=item["expr"],
        dtype=item["dtype"],
        unit=item["unit"],
        description=" ".join(item["description"].split()),
        null_meaning=" ".join(item["null_meaning"].split()),
        owner=ctx.user.user_id,
    )
    try:
        checked = ctx.features.with_user([definition])
    except ExpressionError as exc:
        raise ConfigurationError(exc.message) from exc
    expression = checked.expressions[name]
    reads = {*expression.refs, *expression.uses}
    if reads != set(item["inputs"]):
        raise ConfigurationError(
            f"inputs {sorted(set(item['inputs']))} are not the names the formula reads "
            f"{sorted(reads)}"
        )
    fp = fingerprint(definition)
    existing = find_duplicate(fp, *_declared(ctx))
    if existing is not None:
        return existing, _criterion_on(item, f"feature.{existing}", normalise)
    criterion = _criterion_on(item, f"feature.{name}", normalise)
    stats = dry_run(ctx, definition, _count_criterion(criterion))
    return DraftFormula(
        name=name,
        expr=item["expr"],
        dtype=item["dtype"],
        unit=item["unit"],
        description=definition.description,
        null_meaning=definition.null_meaning,
        inputs=tuple(sorted(reads)),
        criterion=criterion,
        fingerprint=fp.hash,
        dry_run=stats,
    )


def _declared(ctx: ReadContext) -> tuple[list[FeatureDefinition], list[FeatureDefinition]]:
    """The site's expression features, then the trader's own, as ``find_duplicate`` takes them."""
    expressions = ctx.features.expressions.values()
    site = [e.definition for e in expressions if e.scope == "site"]
    own = [e.definition for e in expressions if e.scope != "site"]
    return site, own


def _criterion_on(
    item: Mapping[str, Any], field: str, normalise: Normalise
) -> dict[str, Any] | None:
    raw = item.get("criterion")
    if raw is None:
        return None
    return normalise(raw, field)


def _count_criterion(criterion: dict[str, Any] | None) -> tuple[str, float] | None:
    """``(op, threshold)`` for the dry run, when the criterion is one comparison with a number."""
    if criterion is None or criterion["op"] not in _SYMBOL:
        return None
    value = criterion.get("value")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return _SYMBOL[criterion["op"]], float(value)
