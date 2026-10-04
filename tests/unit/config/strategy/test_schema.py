import pytest

from algotrade.config.strategy.schema import (
    Group,
    Rule,
    parse_group,
    parse_selection,
    parse_strategy,
)
from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError

RULE = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}


def test_parse_nested_groups() -> None:
    group = parse_group({"all": [RULE, {"any": [RULE, {"not": RULE}]}]}, "sel")
    assert group.kind == "all"
    assert isinstance(group.children[1], Group)
    assert len(group.rules()) == 3
    assert parse_group({"all": [{"field": "x", "op": "in", "value": ["a", "b"]}]}, "s").children[
        0
    ] == Rule("x", "in", ("a", "b"))


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"all": [], "any": []}, "exactly one"),
        ({"all": []}, "non-empty list"),
        ({"all": ["x"]}, r"sel\.all\[0\]: expected a table"),
        ({"all": [{"field": "x", "op": "nope", "value": 1}]}, "op must be one of"),
        ({"all": [{"field": "x", "op": "eq"}]}, "needs a 'value'"),
        ({"all": [{"field": "x", "op": "in", "value": "a"}]}, "non-empty list"),
        ({"all": [{"field": "x", "op": "between", "value": [1]}]}, r"between needs \[low, high\]"),
        ({"all": [{"field": "x", "op": "eq", "value": {"a": 1}}]}, "expected a string"),
        ({"all": [{"op": "eq", "value": 1}]}, "string 'field'"),
        ({"all": [{"field": "x", "op": "eq", "value": 1, "extra": 1}]}, "unknown keys"),
    ],
)
def test_group_errors_name_the_path(raw: dict, message: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(ConfigurationError, match=message):
        parse_group(raw, "sel")


def test_null_ops_need_no_value() -> None:
    assert parse_group({"all": [{"field": "x", "op": "is_null"}]}, "s").rules()[0].value is None


def test_selection_validation() -> None:
    sel = parse_selection(
        {
            "name": "top",
            "where": {"all": [RULE]},
            "max_instruments": 5,
            "order_by": "rollup.x@v1.y",
        },
        "s",
    )
    assert (sel.max_instruments, sel.order_by) == (5, "rollup.x@v1.y")
    for raw, message in [
        ({"name": "Bad Name", "where": {"all": [RULE]}}, "invalid selection id"),
        ({"name": "ok"}, "needs a 'where'"),
        ({"name": "ok", "where": {"all": [RULE]}, "max_instruments": 0}, "positive integer"),
        ({"name": "ok", "where": {"all": [RULE]}, "max_instruments": 3}, "order_by"),
        ({"name": "ok", "where": {"all": [RULE]}, "colour": "red"}, "unknown keys"),
    ]:
        with pytest.raises(ConfigurationError, match=message):
            parse_selection(raw, "s")


def test_strategy_validation() -> None:
    base = {"id": "x", "kind": "screener", "impl": "s"}
    cfg = parse_strategy(
        {
            **base,
            "params": {"a": 1},
            "selection": {"name": "inline", "where": {"all": [RULE]}},
            "exports": ["e"],
            "schedule": "nightly",
            "screening": {"min_coverage": 0.5},
        },
        "c",
    )
    assert cfg.params == {"a": 1}
    assert cfg.settings == {"screening": {"min_coverage": 0.5}}
    for raw, message in [
        ({**base, "kind": "bot"}, "kind"),
        ({**base, "impl": 3}, "impl"),
        ({**base, "params": [1]}, "params"),
        ({**base, "selection": 3}, "preset name or a selection table"),
        ({**base, "schedule": "hourly"}, "schedule"),
        ({**base, "exports": "csv"}, "exports"),
        ({**base, "bogus": 1}, "unknown keys"),
        ({**base, "name": " "}, "display name"),
        ({**base, "id": "../etc"}, "invalid config id"),
    ]:
        with pytest.raises(ConfigurationError, match=message):
            parse_strategy(raw, "c")


def test_a_config_may_carry_a_display_name() -> None:
    raw = {"id": "c", "kind": "screener", "impl": "x", "name": "My scan"}
    assert parse_strategy(raw, "c").name == "My scan"
    assert parse_strategy({k: v for k, v in raw.items() if k != "name"}, "c").name is None


def test_user_context_validates_ids() -> None:
    assert UserContext().user_id == "local"
    with pytest.raises(ConfigurationError, match="invalid user id"):
        UserContext("Not/Safe")
