"""Check the phrasebook's structured entries against a catalogue: the part of validation the
loader cannot do (``config/site/drafting/criteria.py`` has no catalogue). A criterion's field
must be a catalogue field, its op must fit the field's type (a number op on a number, ``eq`` /
``in`` on text or a category with its values among the field's categories, ``eq`` / ``ne`` on a
boolean with a boolean), and it must pass the answer's own criterion check
(``answer_schema.check_criterion``), the one definition of a criterion the model's answers use."""

from collections.abc import Collection, Mapping

from algotrade.config.site.drafting.criteria import PhraseCriterion
from algotrade.config.site.llm import Phrase
from algotrade.core.model.fields import NUMERIC_TYPES
from algotrade.core.model.predicates import NO_VALUE_OPS, NUMERIC_OPS
from algotrade.services.drafting.answer_schema import check_criterion
from algotrade.services.read.instruments.catalogue import FeatureInfo


def phrase_criteria(phrase: Phrase) -> tuple[PhraseCriterion, ...]:
    """Every criterion of an entry: the exact ones, or those of its alternatives."""
    return phrase.criteria or tuple(a.criterion for a in phrase.alternatives)


def criterion_problem(criterion: PhraseCriterion, infos: Mapping[str, FeatureInfo]) -> str | None:
    """Why ``criterion`` cannot be used over this catalogue, else ``None``."""
    info = infos.get(criterion.field)
    if info is None:
        return f"{criterion.field}: not in the catalogue"
    if (shape := check_criterion(criterion.as_answer())) is not None:
        return f"{criterion.field}: {shape}"
    if criterion.op in NO_VALUE_OPS:
        return None
    return _type_problem(criterion, info)


def _type_problem(criterion: PhraseCriterion, info: FeatureInfo) -> str | None:
    op, value, name = criterion.op, criterion.value, criterion.field
    members = value if isinstance(value, tuple) else (value,)
    if info.dtype in NUMERIC_TYPES:
        fits = op in NUMERIC_OPS | {"eq", "ne", "in", "not_in"} and all(map(_number, members))
        return None if fits else f"{name}: {op} {value!r} does not fit a number"
    if op in NUMERIC_OPS:
        return f"{name}: {op} needs a number field, this is {info.dtype}"
    if info.dtype == "bool":
        fits = op in ("eq", "ne") and isinstance(value, bool)
        return None if fits else f"{name}: a boolean takes eq / ne with true or false"
    if info.dtype != "str":
        return f"{name}: {op} does not fit {info.dtype}"
    if not all(isinstance(v, str) for v in members):
        return f"{name}: {op} takes text"
    unknown = [v for v in members if info.categories and v not in info.categories]
    return f"{name}: {unknown} not among {list(info.categories)}" if unknown else None


def _number(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def problems(phrases: Collection[Phrase], infos: Mapping[str, FeatureInfo]) -> list[str]:
    """Every problem of every structured entry (``<first word>: <why>``); none: all usable."""
    found: list[str] = []
    for phrase in phrases:
        for criterion in phrase_criteria(phrase):
            if (why := criterion_problem(criterion, infos)) is not None:
                found.append(f"{phrase.say[0]}: {why}")
    return found
