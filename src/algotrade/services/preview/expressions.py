"""Check a formula the Builder is editing before the user names it: parse and type check it
against the user's catalogue (site features + their own), then evaluate it on the request's
session (``ReadContext.session``: ADR 0036, never an older partition of an input), for a small
sample. On a store with no session yet (a ``StoreContext``) the formula is checked, not
sampled. Read-only: nothing is saved (naming and saving is ``services.authoring.user_features``)."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.site.settings import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.services.features import catalogue, read_expressions
from algotrade.services.read.context import ReadContext, Stores
from algotrade.services.views import to_value

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
    session: date | None = None
    missing: list[str] = sorted(checked.stored_columns([name]))
    rows = non_null = 0
    shown: list[SampleValue] = []
    if isinstance(ctx, ReadContext):
        read = read_expressions(ctx.reader, [name], ctx.session.date, features=checked)
        missing = sorted(read.missing)
        session = None if missing else ctx.session.date
    if session is not None:
        frame = read.frame
        present = frame.dropna(subset=[name]).sort_values("instrument_id", kind="stable")
        rows, non_null = len(frame), len(present)
        head = present.head(max(0, min(sample, MAX_SAMPLE)))
        shown = [
            SampleValue(str(i), to_value(v))
            for i, v in zip(head["instrument_id"], head[name], strict=True)
        ]
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
