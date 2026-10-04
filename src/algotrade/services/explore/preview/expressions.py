"""Check a formula the Builder is editing before the user names it: parse and type check it
against the user's catalogue (site features + their own), then evaluate it on the latest
session every stored input has, for a small sample. Read-only: nothing is saved (naming and
saving is ``services.authoring.user_features``)."""

from dataclasses import dataclass
from datetime import date

from algotrade.config.site.settings import FeatureDefinition
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.ids import validate_id
from algotrade.services.explore.store import ReadStore
from algotrade.services.features import catalogue, read_expressions
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
    session: date | None  # the session sampled (None: an input has nothing stored)
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
    store: ReadStore, expr: str, user: str | None = None, sample: int = 5
) -> ExpressionCheck:
    """``expr`` type checked for ``user`` (default: the store's) and sampled. An invalid
    formula is a ``ConfigurationError`` with its position."""
    who = validate_id("user", user if user is not None else store.user.user_id)
    if not isinstance(expr, str) or not expr.strip():
        raise ConfigurationError("expr: expected a formula")
    fs = catalogue(store.configs, who)
    found = fs.formula_type(expr, "expr")
    if found.kind not in DTYPE_OF:
        raise ConfigurationError(f"expr: the formula gives {found}, not a value")
    name = next(f"check_{n}" for n in range(len(fs.expressions) + 1)
                if f"check_{n}" not in fs.expressions)  # fmt: skip
    checked = fs.with_user([_definition(name, expr, found.kind, who)])
    feature = checked.expressions[name].feature
    reader = store.reader
    latest = [max(reader.dates(t), default=None) for t in checked.stored_columns([name])]
    session = None if not latest or None in latest else min(d for d in latest if d is not None)
    rows = non_null = 0
    shown: list[SampleValue] = []
    if session is not None:
        frame = read_expressions(reader, [name], session, features=checked).frame
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
        rows=rows,
        non_null=non_null,
        sample=shown,
    )
