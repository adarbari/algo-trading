"""Rules inside an outcome (ADR 0088, design 2.4, 2.4a, 2.13): case values split into literals
and cases; ``[outcome.entry]``; the canonical form of a rule (a reordered group has one identity);
the exit settings compiled to one ordered rule list; each rule checked against the catalogue at
its use site; and what a run does not yet apply is refused at load."""

from dataclasses import asdict
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.positions.fields import is_credit
from algotrade.config.edges.positions.spec import (
    check_edge,
    check_rules,
    exit_delay,
    exit_rules,
)
from algotrade.config.edges.positions.templates import Leg, Template, load_templates
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.configs import field_catalog
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.positions.test_spec import PUT, WHERE, document, put

SHIPPED = FileConfigStore(REPO_ROOT / "config")
TEMPLATES = load_templates(SHIPPED)
CATALOG = field_catalog(SHIPPED)
IV = "rollup.iv_history@v2.iv_rank_252d"
NDX = "market.market_trend@v2.ndx_drawdown_252d"
SPX = "market.market_trend@v2.spx_drawdown_252d"  # personal
DTE = {"field": "position.dte", "op": "lt", "value": 5}
HIGH_IV = {"all": [{"field": IV, "op": "gte", "value": 0.8}]}


def parse(**changes: Any) -> Any:
    return parse_edge(put(**changes), "drift", WHERE)


def tenor_cases() -> dict[str, Any]:
    return {"cases": [{"when": HIGH_IV, "value": 30}], "default": 45}


def test_a_case_table_leaves_its_default_as_the_literal_and_the_cases_beside_it() -> None:
    o = parse(tenor_days=tenor_cases()).outcome
    assert o.tenor_days == 45
    [cv] = o.position.cases
    assert (cv.name, cv.default, [c.value for c in cv.cases]) == ("tenor_days", 45, [30])


def test_a_case_table_in_the_exit_settings_and_in_a_variant() -> None:
    exit_cases = {**PUT["exit"], "take_profit": {"cases": [{"when": HIGH_IV, "value": 0.25}],
                                                  "default": 0.5}}  # fmt: skip
    o = parse(exit=exit_cases).outcome
    assert o.position.exit.take_profit == 0.5
    assert [c.name for c in o.position.cases] == ["take_profit"]
    doc = {**put(), "variants": [{"id": "iv", "outcome": {"tenor_days": tenor_cases()}}]}
    assert (
        parse_edge(doc, "drift", WHERE).variants[0].outcome.position.cases[0].name == "tenor_days"
    )


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ({"cases": [{"when": HIGH_IV, "value": 9999}], "default": 45}, "tenor_days"),
        ({"cases": [{"when": HIGH_IV, "value": 30.5}], "default": 45}, "tenor_days"),
        ({"cases": [{"when": HIGH_IV, "value": 30}]}, "default"),
        ({"cases": [], "default": 45}, "non-empty cases"),
        ({"cases": [{"value": 30}], "default": 45}, "needs when and value"),
        ({"cases": [{"when": {"x": 1}, "value": 30}], "default": 45}, "exactly one of"),
        ({"cases": [{"when": HIGH_IV, "value": 30}], "default": 45, "x": 1}, "unknown keys"),
    ],
)
def test_a_case_table_is_typed_fail_closed(value: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        parse(tenor_days=value)


def test_a_case_needs_a_position() -> None:
    o = {"kind": "option_pnl", "horizon_sessions": [21], "benchmark": "none",
         "start_offset_sessions": 1, "tenor_days": tenor_cases(), "structure": "put_short",
         "strike_delta": 0.2}  # fmt: skip
    with pytest.raises(ConfigurationError, match="cases: needs a position"):
        parse_edge(document(schedule="every_session", outcome=o), "drift", WHERE)


def test_position_cases_choose_among_templates_of_one_kind() -> None:
    ok = {"cases": [{"when": HIGH_IV, "value": "put_spread"}], "default": "short_put"}
    check_rules(parse(position=ok), WHERE, CATALOG, TEMPLATES)
    mixed = {"cases": [{"when": HIGH_IV, "value": "long_shares"}], "default": "short_put"}
    with pytest.raises(ConfigurationError, match="templates of one kind"):
        check_rules(parse(position=mixed), WHERE, CATALOG, TEMPLATES)
    unknown = {"cases": [{"when": HIGH_IV, "value": "nope"}], "default": "short_put"}
    with pytest.raises(ConfigurationError, match="no position template named"):
        check_rules(parse(position=unknown), WHERE, CATALOG, TEMPLATES)


def test_a_reordered_group_has_one_identity() -> None:
    a = {"all": [{"field": IV, "op": "gte", "value": 0.8}, {"field": NDX, "op": "lt", "value": 0}]}
    b = {"all": [{"field": NDX, "op": "lt", "value": 0}, {"field": IV, "op": "gte", "value": 0.8}]}
    ea, eb = (parse_edge({**put(), "gate": g}, "drift", WHERE) for g in (a, b))
    assert ea.gate == eb.gate
    assert identity_dict(asdict(ea)) == identity_dict(asdict(eb))
    na = {"all": [{"not": {"any": [a, HIGH_IV]}}]}
    nb = {"all": [{"not": {"any": [HIGH_IV, b]}}]}
    xa, xb = (parse_edge({**put(), "gate": g}, "drift", WHERE) for g in (na, nb))
    assert xa.gate == xb.gate


def test_the_entry_condition_parses_for_both_kinds() -> None:
    entry = {"when": HIGH_IV, "within_sessions": 3}
    o = parse(entry=entry).outcome
    assert o.entry is not None and o.entry.within_sessions == 3
    shares = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
              "start_offset_sessions": 1, "entry": {"when": HIGH_IV}}  # fmt: skip
    assert parse_edge(document(outcome=shares), "drift", WHERE).outcome.entry.within_sessions == 1
    for bad, match in (({"within_sessions": 3}, "when: required"),
                       ({"when": HIGH_IV, "within_sessions": 0}, "within_sessions"),
                       ({"when": HIGH_IV, "within_sessions": 99}, "at most"),
                       ({"when": HIGH_IV, "x": 1}, "unknown keys")):  # fmt: skip
        with pytest.raises(ConfigurationError, match=match):
            parse(entry=bad)


def test_what_no_run_applies_yet_is_refused_at_load() -> None:
    entry = {"when": HIGH_IV}
    with pytest.raises(ConfigurationError, match=r"entry: not applied by any run yet \(E13\)"):
        check_edge(parse(entry=entry), WHERE, TEMPLATES)
    with pytest.raises(ConfigurationError, match=r"case values: not applied.*\(E13\)"):
        check_edge(parse(tenor_days=tenor_cases()), WHERE, TEMPLATES)


def test_the_exit_settings_compile_to_one_ordered_rule_list() -> None:
    when = {"any": [{"field": "position.distance_to_strike_pct", "op": "gt", "value": 0.02}]}
    spec = parse(exit={**PUT["exit"], "when": when}).outcome.position
    rules = exit_rules(spec.exit)
    assert [r.kind for r in rules] == ["TAKE_PROFIT", "STOP_LOSS", "EXIT_DTE", "CONDITION"]
    take, stop, dte, _cond = (
        r.rule.children[0] if r.kind != "CONDITION" else r.rule for r in rules
    )
    assert (take.field, take.op, take.value) == ("position.profit_share_of_credit", "gte", 0.5)
    assert (stop.op, stop.value) == ("lte", -2.0)
    assert (dte.field, dte.op, dte.value) == ("position.dte", "lte", 21)
    assert exit_rules(None) == ()


def test_a_rule_acts_at_t_when_position_only_and_at_t_plus_1_when_it_reads_a_catalogue_field() -> (
    None
):
    rules = exit_rules(parse(exit={**PUT["exit"], "when": HIGH_IV}).outcome.position.exit)
    assert [exit_delay(r.rule) for r in rules] == [0, 0, 0, 1]
    mixed = {"all": [{"field": "position.dte", "op": "lt", "value": 5}, *HIGH_IV["all"]]}
    mixed_rules = exit_rules(parse(exit={"when": mixed}).outcome.position.exit)
    assert exit_delay(mixed_rules[0].rule) == 1


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"gate": {"all": [{"field": IV, "op": "gt", "value": 1}]}}, "instrument-level.*'gate'"),
        ({"gate": {"all": [{"field": SPX, "op": "gt", "value": 0}]}}, "personal-licensed"),
        ({"gate": {"all": [{"field": NDX, "op": "is_null"}]}}, "never null-tested"),
        ({"entry": {"when": {"all": [{"field": "position.dte", "op": "lt", "value": 5}]}}},
         r"unknown field 'position\.dte'"),
        ({"entry": {"when": {"all": [{"field": "nope.x", "op": "lt", "value": 5}]}}},
         "unknown field"),
        ({"tenor_days": {"cases": [{"when": {"all": [DTE]}, "value": 30}], "default": 45}},
         r"unknown field 'position\.dte'"),
        ({"exit": {"when": {"all": [{"field": NDX, "op": "is_null"}]}}}, "never null-tested"),
    ],
)  # fmt: skip
def test_each_rule_is_checked_at_its_own_use_site(changes: dict[str, Any], match: str) -> None:
    doc = put(**{k: v for k, v in changes.items() if k not in ("gate",)})
    if "gate" in changes:
        doc["gate"] = changes["gate"]
    with pytest.raises(ConfigurationError, match=match):
        check_rules(parse_edge(doc, "drift", WHERE), WHERE, CATALOG, TEMPLATES)


def test_the_right_rules_pass_at_their_sites() -> None:
    doc = {
        **put(entry={"when": HIGH_IV}, tenor_days=tenor_cases(),
              exit={"when": {"any": [{"field": "position.distance_to_strike_pct", "op": "gt",
                                      "value": 0.02}, *HIGH_IV["all"]]}}),
        "gate": {"all": [{"field": NDX, "op": "lt", "value": 0}]},
    }  # fmt: skip
    check_rules(parse_edge(doc, "drift", WHERE), WHERE, CATALOG, TEMPLATES)


def test_a_position_field_that_does_not_apply_to_the_templates_legs_is_refused() -> None:
    shares = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
              "start_offset_sessions": 1, "position": "long_shares",
              "exit": {"when": {"all": [DTE]}}}  # fmt: skip
    edge = parse_edge(document(outcome=shares), "drift", WHERE)
    with pytest.raises(ConfigurationError, match=r"unknown field 'position\.dte'"):
        check_rules(edge, WHERE, CATALOG, TEMPLATES)


def test_every_branch_of_a_position_case_is_checked_like_the_default() -> None:
    to_straddle = {"cases": [{"when": HIGH_IV, "value": "short_straddle"}], "default": "short_put"}
    with pytest.raises(ConfigurationError, match="has no leg chosen by delta"):
        check_edge(parse(position=to_straddle), WHERE, TEMPLATES)
    cases_on_shares = {"cases": [{"when": HIGH_IV, "value": "short_shares"}],
                       "default": "long_shares"}  # fmt: skip
    shares = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
              "start_offset_sessions": 1, "position": cases_on_shares}  # fmt: skip
    with pytest.raises(ConfigurationError, match="not the position of side"):
        check_edge(parse_edge(document(outcome=shares), "drift", WHERE), WHERE, TEMPLATES)
    lacking = {"cases": [{"when": HIGH_IV, "value": "put_spread"}], "default": "short_put"}
    doc = put(position=lacking, exit={"when": {"all": [DTE]}}, strike_delta=None)
    check_rules(parse_edge(doc, "drift", WHERE), WHERE, CATALOG, TEMPLATES)  # both have dte


def test_which_templates_are_credit_and_a_case_axis_is_not_a_grid_axis() -> None:
    debit = Template("long_put", (Leg("option", 1, "P", "atm"),), "max_loss")
    assert not is_credit(debit)
    shorts = Leg("option", -1, "P", "delta", 0.16)
    wing = Leg("option", 1, "P", "otm_pct", None, 0.05)
    assert is_credit(Template("condor", (shorts, wing), "max_loss"))
    near = (Leg("option", -1, "C", "atm"), Leg("option", 1, "C", "atm"))
    assert not is_credit(Template("calendar", near, "max_loss"))
    grid = [{"prefix": "g", "tenor_days": [7, 30]}]
    doc = {**put(tenor_days=tenor_cases()), "variant_grid": grid}
    with pytest.raises(ConfigurationError, match="also case-valued"):
        check_edge(parse_edge(doc, "drift", WHERE), WHERE, TEMPLATES)


def test_a_position_outcomes_identity_drops_absent_cases_and_exit_condition() -> None:
    o = identity_dict(asdict(parse().outcome))
    assert "cases" not in o["position"] and "when" not in o["position"]["exit"]
