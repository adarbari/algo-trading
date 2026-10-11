"""Check a formula the Builder is editing before the user names it: parse and type check it
against the user's catalogue (site features + their own), then evaluate it on the request's
session (``ReadContext.session``: ADR 0036, never an older partition of an input), for a small
sample. On a store with no session yet (a ``StoreContext``) the formula is checked, not
sampled. Read-only: nothing is saved (naming and saving is ``services.authoring.user_features``).
``dry_run`` is the same evaluation as statistics over every row of the session (no-value rate,
range, how many pass a criterion), for the drafting answer."""

from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.services.features import catalogue, read_expressions
from algotrade.services.read.context import ReadContext, Stores
from algotrade.services.views import to_value

CRITERION_OPS = ("<", "<=", ">", ">=", "==", "!=")

CHECK_THEME = "check"
DTYPE_OF = {"num": "float", "bool": "bool", "str": "str", "date": "date"}
UNIT_OF = {"num": "ratio", "bool": "flag", "str": "text", "date": "date"}
MAX_SAMPLE = 50


@dataclass(frozen=True)
class SampleValue:
    instrument_id: str
    value: object


@dataclass(frozen=True)
class ExpressionCheck:
    expr: str
    type: str  # num / bool / str / date
    dtype: str  # what a saved feature would declare
    categories: list[str] | None  # the closed set a str formula can give (None: open)
    inputs: list[str]  # stored features (group.column@vN) and expression features read
    licence: str  # the strictest licence of what it reads (ADR 0028)
    session: date | None  # the session sampled (None: not sampled, ``missing`` says why)
    missing: list[str]  # the inputs' tables with no partition for the session (UNKNOWN)
    rows: int
    non_null: int
    sample: list[SampleValue]


def _definition(name: str, expr: str, kind: str, user: str) -> FeatureDefinition:
    return FeatureDefinition(
        name=name,
        theme=CHECK_THEME,
        expr=expr,
        dtype=DTYPE_OF[kind],
        unit=UNIT_OF[kind],
        description="a formula being checked in the Builder (not saved)",
        null_meaning="an input is null",
        owner=user,
    )


def _evaluate(ctx: Stores, checked: FeatureSet, name: str) -> tuple[date | None, list[str], Any]:
    """The session sampled (None: not sampled), the inputs' tables missing for it, and the
    frame of ``name`` on it (None when not sampled)."""
    missing: list[str] = sorted(checked.stored_columns([name]))
    if not isinstance(ctx, ReadContext):
        return None, missing, None
    read = read_expressions(ctx.reader, [name], ctx.session.date, features=checked)
    missing = sorted(read.missing)
    if missing:
        return None, missing, None
    return ctx.session.date, missing, read.frame


def _samples(present: Any, name: str, sample: int) -> list[SampleValue]:
    head = present.head(max(0, min(sample, MAX_SAMPLE)))
    return [
        SampleValue(str(i), to_value(v))
        for i, v in zip(head["instrument_id"], head[name], strict=True)
    ]


def check_expression(
    ctx: Stores, expr: str, user: str | None = None, sample: int = 5
) -> ExpressionCheck:
    """``expr`` type checked for ``user`` (default: the context's) and sampled on
    ``ctx.session`` (a ``ReadContext``; a ``StoreContext``: an empty store, not sampled). An
    invalid formula is a ``ConfigurationError`` with its position."""
    who = validate_id("user", user if user is not None else ctx.user.user_id)
    if not isinstance(expr, str) or not expr.strip():
        raise ConfigurationError("expr: expected a formula")
    fs = catalogue(ctx.configs, who)
    found = fs.formula_type(expr, "expr")
    if found.kind not in DTYPE_OF:
        raise ConfigurationError(f"expr: the formula gives {found}, not a value")
    name = next(f"check_{n}" for n in range(len(fs.expressions) + 1)
                if f"check_{n}" not in fs.expressions)  # fmt: skip
    checked = fs.with_user([_definition(name, expr, found.kind, who)])
    feature = checked.expressions[name].feature
    session, missing, frame = _evaluate(ctx, checked, name)
    rows = non_null = 0
    shown: list[SampleValue] = []
    if frame is not None:
        present = frame.dropna(subset=[name]).sort_values("instrument_id", kind="stable")
        rows, non_null = len(frame), len(present)
        shown = _samples(present, name, sample)
    return ExpressionCheck(
        expr=expr,
        type=found.kind,
        dtype=feature.dtype,
        categories=sorted(found.categories) if found.categories is not None else None,
        inputs=list(feature.inputs),
        licence=feature.licence,
        session=session,
        missing=missing,
        rows=rows,
        non_null=non_null,
        sample=shown,
    )


@dataclass(frozen=True)
class DryRun:
    """A formula's values over the whole session: what a trader sees before accepting it."""

    session: date | None  # the session read (None: not read, ``missing`` says why)
    missing: list[str]
    rows: int  # rows checked
    no_value_rate: float | None  # share of rows with no value (None: no rows)
    minimum: float | None  # numeric formulas only
    maximum: float | None
    criterion_pass: int | None  # rows passing ``value <op> threshold`` (None: no criterion)
    sample: list[SampleValue]  # up to MAX_DRY_RUN_SAMPLE rows


MAX_DRY_RUN_SAMPLE = 5


def dry_run(
    ctx: Stores,
    definition: FeatureDefinition,
    criterion: tuple[str, float] | None = None,
) -> DryRun:
    """``definition`` evaluated for ``ctx.user`` over every row of ``ctx.session`` (read-only:
    nothing is saved; ``definition`` may reuse the name of an existing feature). ``criterion``
    is ``(op, threshold)``, counted over the rows that have a value. A formula that does not
    check raises ``ConfigurationError``; a context with no session, or an input missing for it,
    gives a ``DryRun`` with ``session`` None and no statistics."""
    who = validate_id("user", ctx.user.user_id)
    if criterion is not None and criterion[0] not in CRITERION_OPS:
        raise ConfigurationError(
            f"criterion: operator {criterion[0]!r} is not one of {CRITERION_OPS}"
        )
    fs = catalogue(ctx.configs, who)
    found = fs.formula_type(definition.expr, "expr")
    if found.kind not in DTYPE_OF:
        raise ConfigurationError(f"expr: the formula gives {found}, not a value")
    name = next(f"check_{n}" for n in range(len(fs.expressions) + 1)
                if f"check_{n}" not in fs.expressions)  # fmt: skip
    checked = fs.with_user(
        [replace(_definition(name, definition.expr, found.kind, who), params=definition.params)]
    )
    session, missing, frame = _evaluate(ctx, checked, name)
    if frame is None:
        return DryRun(session, missing, 0, None, None, None, None, [])
    present = frame.dropna(subset=[name]).sort_values("instrument_id", kind="stable")
    rows = len(frame)
    lo = hi = None
    if found.kind == "num" and len(present):
        lo, hi = float(present[name].min()), float(present[name].max())
    passed = None
    if criterion is not None:
        op, threshold = criterion
        values = present[name]
        passed = int(
            {
                "<": values < threshold,
                "<=": values <= threshold,
                ">": values > threshold,
                ">=": values >= threshold,
                "==": values == threshold,
                "!=": values != threshold,
            }[op].sum()
        )
    return DryRun(
        session=session,
        missing=missing,
        rows=rows,
        no_value_rate=(rows - len(present)) / rows if rows else None,
        minimum=lo,
        maximum=hi,
        criterion_pass=passed,
        sample=_samples(present, name, MAX_DRY_RUN_SAMPLE),
    )
