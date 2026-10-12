"""B1 formulas of a screen draft (ADR 0041, amended 2026-10-11): a concept the catalogue lacks
that is a same-session expression over existing features. The model proposes each as
``{name, expr, dtype, unit, description, null_meaning, inputs, criterion}``; this module
decides what the server offers the trader, never the model:

- the shape, the ``draft_`` name (no site or own feature shadowed, no repeat) and the formula,
  type-checked as a user feature (``FeatureSet.with_user``, as ``services.authoring``
  does), whose ``inputs`` must be exactly the names it reads;
- the fingerprint (``features.expressions.fingerprint``), before the name is checked: a formula
  equal to a site feature or the trader's own (a re-proposed ``draft_x`` already saved), or one
  that is just a stored column, is dropped and its criterion rewritten onto that field (the
  caller places it; a unit that differs is noted, a percent against a fraction drops the
  criterion); an invalid one is dropped with the reason (``formulas_dropped``);
- a dry run on the request's session (``dry_run_all``, once, on the accepted draft:
  ``services.preview.dry_run``: no-value rate, range, how many rows pass the criterion, a few
  samples) so the trader sees what accepting it does; it never fails the draft (a read that
  breaks leaves the formula unsampled, with a note). At most ``MAX_FORMULAS`` are checked.

A kept formula is *pending*: nothing is saved or put in the draft document; the formula and its
criterion travel together until the trader accepts (the UI saves it as their own feature).
Reads the catalogue and the session; writes nothing."""

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import AlgoTradeError, ConfigurationError
from algotrade.features.expressions.fingerprint import find_duplicate, fingerprint
from algotrade.features.expressions.nodes import ExpressionError, Ref
from algotrade.services.drafting.answer_schema import FORMULA, check_item
from algotrade.services.drafting.parts.model import part_tag
from algotrade.services.preview.expressions import DryRun, dry_run
from algotrade.services.read.context import ReadContext

MAX_FORMULAS = 3  # checked per answer; the rest are cut, with a note
PREFIX = "draft_"
THEME = "draft"
_NAME = re.compile(r"^draft_[a-z][a-z0-9_]{0,55}$")
_SYMBOL = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "==", "ne": "!="}

log = logging.getLogger(__name__)
UNSAMPLED = DryRun(None, [], 0, None, None, None, None, [])  # not run, or the run failed

# What turns a raw criterion item and its field into the draft's criterion table entry
# (``screens._criterion``: raises ``ConfigurationError``).
Normalise = Callable[[Mapping[str, Any], str], dict[str, Any]]


@dataclass(frozen=True)
class DraftFormula:
    """A formula that checked: pending until the trader accepts it. ``dry_run`` is
    ``UNSAMPLED`` until ``dry_run_all`` has run it."""

    name: str
    expr: str
    dtype: str
    unit: str
    description: str
    null_meaning: str
    inputs: tuple[str, ...]
    criterion: dict[str, Any] | None  # the criterion on ``feature.<name>``, pending with it
    fingerprint: str
    dry_run: DryRun = UNSAMPLED
    pending: bool = True  # never saved or in the document until the trader accepts it
    part: str | None = None  # the part id the model tagged it with (explained parts)


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
    rewritten_parts: Mapping[str, str | None] = field(default_factory=dict)  # name -> part tag


@dataclass(frozen=True)
class _Repeat:
    """A formula that is an existing field: ``label`` names it, ``field`` is the criterion's."""

    label: str
    field: str
    unit: str


def check_formulas(
    ctx: ReadContext, proposal: Mapping[str, Any], normalise: Normalise
) -> FormulaOutcome:
    """Every proposed formula of ``proposal`` (the first ``MAX_FORMULAS``) validated for
    ``ctx``'s user, as above; no dry run (``dry_run_all`` does that, once)."""
    raw = proposal.get("formulas")
    items = raw if isinstance(raw, list) else []
    kept: list[DraftFormula] = []
    dropped: list[DroppedFormula] = []
    rewritten: dict[str, dict[str, Any]] = {}
    rewritten_parts: dict[str, str | None] = {}
    notes: list[str] = []
    if len(items) > MAX_FORMULAS:
        notes.append(
            f"{len(items) - MAX_FORMULAS} formulas beyond the first {MAX_FORMULAS} were cut"
        )
    seen: set[str] = set()
    for n, item in enumerate(items[:MAX_FORMULAS], 1):
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
            kept.append(replace(result, part=part_tag(item)))
            continue
        dropped.append(
            DroppedFormula(name, f"the same as the existing feature {result.label}", result.label)
        )
        notes.append(f"{name} is {result.label}: its criterion uses that field")
        criterion = _rewrite(item, result, normalise, notes, name)
        if criterion is not None:
            rewritten[name] = criterion
            rewritten_parts[name] = part_tag(item)
    return FormulaOutcome(tuple(kept), tuple(dropped), rewritten, tuple(notes), rewritten_parts)


def dry_run_all(
    ctx: ReadContext, formulas: tuple[DraftFormula, ...]
) -> tuple[tuple[DraftFormula, ...], tuple[str, ...]]:
    """``formulas`` with their dry run on ``ctx``'s session, and a note for each run that
    failed (the formula is then offered unsampled: a dry run never fails the draft)."""
    out: list[DraftFormula] = []
    notes: list[str] = []
    for f in formulas:
        definition = FeatureDefinition(
            f.name, THEME, f.expr, f.dtype, f.unit, f.description, f.null_meaning,
            owner=ctx.user.user_id,
        )  # fmt: skip
        try:
            stats = dry_run(ctx, definition, _count_criterion(f.criterion))
        except (OSError, AlgoTradeError, ValueError) as exc:  # the store's read errors
            log.warning("dry run of %s failed: %s: %s", f.name, type(exc).__name__, exc)
            notes.append(f"{f.name}: the dry run could not be made ({type(exc).__name__})")
            stats = UNSAMPLED
        out.append(replace(f, dry_run=stats))
    return tuple(out), tuple(notes)


def _name_of(item: Any, n: int) -> str:
    name = item.get("name") if isinstance(item, Mapping) else None
    return name if isinstance(name, str) and name else f"formula_{n}"


def _check(
    ctx: ReadContext, item: Mapping[str, Any], normalise: Normalise
) -> DraftFormula | _Repeat:
    name = item["name"]
    if not _NAME.match(name):
        raise ConfigurationError(
            f"the name must be {PREFIX} followed by a-z, 0-9 and _ (at most 61 characters)"
        )
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
    fp = fingerprint(definition)
    existing = find_duplicate(fp, *_declared(ctx))
    if existing is not None:  # before the name check: a re-proposed saved formula is a repeat
        return _Repeat(
            existing, f"feature.{existing}", ctx.features.expressions[existing].feature.unit
        )
    if ctx.features.feature(name) is not None:
        raise ConfigurationError(f"{name} is already a feature of this catalogue")
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
    if isinstance(expression.node, Ref):  # a bare reference is the field it names
        return _column(ctx, expression.node.name, expression.feature.inputs)
    return DraftFormula(
        name=name,
        expr=item["expr"],
        dtype=item["dtype"],
        unit=item["unit"],
        description=definition.description,
        null_meaning=definition.null_meaning,
        inputs=tuple(sorted(reads)),
        criterion=_criterion_on(item, f"feature.{name}", normalise),
        fingerprint=fp.hash,
    )


def _column(ctx: ReadContext, ref: str, inputs: tuple[str, ...]) -> _Repeat:
    """The field a lone reference names: a stored column (``group.column``) or a feature."""
    if "." not in ref:
        return _Repeat(ref, f"feature.{ref}", ctx.features.expressions[ref].feature.unit)
    stored = ctx.features.feature(inputs[0])
    if stored is None:  # pragma: no cover - a checked reference is in the catalogue
        raise ConfigurationError(f"{ref} is not a stored feature")
    return _Repeat(ref, stored.field, stored.unit)


def _rewrite(
    item: Mapping[str, Any], repeat: _Repeat, normalise: Normalise, notes: list[str], name: str
) -> dict[str, Any] | None:
    """The proposed criterion on the existing field, only when both are in the same unit: a
    threshold in another unit would filter on the wrong scale, so it is dropped, with a note."""
    unit = item["unit"]
    if unit != repeat.unit:
        notes.append(
            f"{name}: its criterion was dropped (proposed in {unit}, {repeat.label} is in "
            f"{repeat.unit})"
        )
        return None
    return _criterion_on(item, repeat.field, normalise)


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
