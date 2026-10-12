"""Structured phrasebook thresholds (``[[phrase.criterion]]`` / ``[[phrase.alternative]]``): the
loader accepts the shapes of an answer criterion and every refusal names the file and entry."""

from typing import Any

import pytest

from algotrade.config.site.llm import PhrasebookSettings
from algotrade.core.model.errors import ConfigurationError


def load(*extra: dict[str, Any], **entry: Any) -> PhrasebookSettings:
    return PhrasebookSettings.from_document(
        {"phrase": [{"say": ["w"], "fields": ["f"], "hint": "h", **entry}, *extra]}
    )


def crit(**kw: Any) -> dict[str, Any]:
    return {"field": "feature.x", "op": "gte", "value": 1, **kw}


def test_a_criterion_loads_with_its_mode_tolerance_and_on_miss() -> None:
    (p,) = load(
        criterion=[crit(mode="soft", tolerance={"relative": 0.2}, on_miss="LIQUIDITY_RISK")]
    ).phrases
    (c,) = p.criteria
    assert (c.field, c.op, c.value, c.mode) == ("feature.x", "gte", 1, "soft")
    assert c.as_answer() == {
        "field": "feature.x",
        "op": "gte",
        "value": 1,
        "mode": "soft",
        "tolerance": {"relative": 0.2},
        "on_miss": "LIQUIDITY_RISK",
    }
    assert c.short() == "x gte 1 soft tol relative 0.2"


def test_list_and_valueless_ops() -> None:
    (p,) = load(
        criterion=[
            crit(op="in", value=["A", "B"]),
            crit(op="between", value=[1, 2]),
            {"field": "feature.y", "op": "not_null"},
        ]
    ).phrases
    assert p.criteria[0].as_answer()["value"] == ["A", "B"]
    assert "value" not in p.criteria[2].as_answer()
    assert p.criteria[0].short() == "x in [A,B]"


def test_alternatives_have_labels_a_default_and_are_not_exact() -> None:
    (p,) = load(
        alternative=[
            {"label": "10M", **crit(value=10)},
            {"label": "50M", **crit(value=50)},
        ],
        default="50M",
    ).phrases
    assert [a.label for a in p.alternatives] == ["10M", "50M"] and p.default_index == 1
    assert p.criteria == ()
    assert load(alternative=[{"label": "a", **crit()}]).phrases[0].default_index == 0


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"criterion": [crit(field="")]}, r"\[\[phrase\]\]\[0\] \[\[criterion\]\]\[0\] field"),
        ({"criterion": [crit(op="above")]}, r"criterion\]\]\[0\] op"),
        ({"criterion": [crit(mode="loud")]}, r"mode: expected one of"),
        ({"criterion": [crit(value=None)]}, r"gte needs a value"),
        ({"criterion": [crit(value="x")]}, r"gte takes a number"),
        ({"criterion": [crit(value=True)]}, r"gte takes a number"),
        ({"criterion": [crit(op="in", value=[])]}, r"non-empty list"),
        ({"criterion": [crit(op="between", value=[2, 1])]}, r"low <= high"),
        ({"criterion": [crit(op="between", value=[1])]}, r"two numbers"),
        ({"criterion": [{"field": "f", "op": "is_null", "value": 1}]}, r"takes no value"),
        ({"criterion": [crit(tolerance=0.1)]}, r"a hard criterion has none"),
        ({"criterion": [crit(mode="soft", tolerance=-1)]}, r"tolerance: expected"),
        ({"criterion": [crit(mode="score", on_miss="WATCH")]}, r"on_miss: a soft criterion"),
        ({"criterion": [crit(mode="soft", on_miss="X")]}, r"on_miss: a soft criterion"),
        ({"criterion": [crit(color="x")]}, r"unknown keys"),
        ({"criterion": [crit()], "alternative": [{"label": "a", **crit()}]}, r"exclusive"),
        ({"default": "a"}, r"default: only with alternatives"),
        ({"alternative": [crit()]}, r"label: expected a short"),
        (
            {"alternative": [{"label": "a", **crit()}, {"label": "a", **crit()}]},
            r"alternative labels listed more than once",
        ),
        ({"alternative": [{"label": "a", **crit()}], "default": "b"}, r"default: 'b'"),
        ({"criterion": "x"}, r"expected a list of tables"),
    ],
)
def test_refusals_name_the_entry(entry: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message) as err:
        load(**entry)
    assert "phrasebook.toml [[phrase]][0]" in str(err.value)
