"""The position of an outcome (ADR 0088, design 2.4, 2.4a): the ``position`` key with its option
parameters and ``[outcome.exit]`` round trip through ``parse_edge`` and are checked against the
site's templates where the edge loads; ``position`` with ``structure`` is refused, an entry at D's
close is refused, an edge that never names the keys hashes as before."""

from dataclasses import asdict, replace
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.named import DELTA_EQUIVALENT
from algotrade.config.edges.positions.chain import grain_name, reads_share_path
from algotrade.config.edges.positions.spec import (
    SLEEVE_BASE,
    ExitSettings,
    PositionSpec,
    check_edge,
    exits_digest,
)
from algotrade.config.edges.positions.templates import load_templates
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.forward.settle import outcome_hash
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import WHERE, document

TEMPLATES = load_templates(FileConfigStore(REPO_ROOT / "config"))
GATE = {"all": [{"field": "market.vix_close", "op": "lt", "value": 30}]}
PUT = {
    "kind": "option_pnl", "horizon_sessions": [21], "benchmark": "none",
    "start_offset_sessions": 1, "tenor_days": 30, "position": "short_put", "strike_delta": 0.2,
    "expiry_cycle": "weekly", "skip_report_in_life": True, "book": True,
    "exit": {"take_profit": 0.5, "stop_loss": 2.0, "exit_dte": 21},
}  # fmt: skip


NAMED = {"where": {"all": [{"field": "instrument.symbol", "op": "in", "value": ["SPY"]}]}}


def put(**changes: Any) -> dict[str, Any]:
    body = {k: v for k, v in {**PUT, **changes}.items() if v is not None}
    return document(schedule="every_session", outcome=body, **{"baselines": []})


def test_a_position_round_trips() -> None:
    o = parse_edge(put(), "drift", WHERE).outcome
    assert o.position == PositionSpec("short_put", "weekly", True, True, ExitSettings(0.5, 2.0, 21))
    assert (o.strike_delta, o.tenor_days, o.structure) == (0.2, 30, None) and o.basis == "chain"
    check_edge(parse_edge(put(), "drift", WHERE), WHERE, TEMPLATES)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"structure": "put_short"}, "names a position template"),
        ({"start_offset_sessions": 0}, "start_offset_sessions: the screen runs after"),
        ({"exit": {}}, "names none of"),
        ({"exit": {"take_profit": 1.5}}, "take_profit"),
        ({"exit": {"when": {}}}, "exactly one of"),
        ({"exit": {"x": 1}}, "unknown keys"),
        ({"expiry_cycle": "daily"}, "expiry_cycle"),
        ({"position": "Bad Id"}, "invalid position id"),
        ({"strike_delta": 0.9}, "strike_delta"),
        ({"tenor_days": None}, "tenor_days"),
    ],
)
def test_a_position_is_refused_fail_closed(changes: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        parse_edge(put(**changes), "drift", WHERE)


def test_option_parameters_need_a_position() -> None:
    o = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
         "start_offset_sessions": 1, "book": True}  # fmt: skip
    with pytest.raises(ConfigurationError, match="book: needs a position"):
        parse_edge(document(outcome=o), "drift", WHERE)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"position": "nothing"}, "no position template named"),
        ({"position": "long_shares", "exit": None, "book": None, "skip_report_in_life": None,
          "expiry_cycle": None, "tenor_days": 30}, "does not fit a option_pnl"),
    ],
)  # fmt: skip
def test_the_template_must_exist_and_fit_the_kind(changes: dict[str, Any], match: str) -> None:
    edge = parse_edge(put(**changes), "drift", WHERE)
    with pytest.raises(ConfigurationError, match=match):
        check_edge(edge, WHERE, TEMPLATES)


def test_a_share_position_is_its_sides_template_and_takes_no_option_parameters() -> None:
    def shares(**changes: Any) -> Any:
        body = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
                "start_offset_sessions": 1, "position": "long_shares", **changes}  # fmt: skip
        return parse_edge(document(outcome=body), "drift", WHERE)

    check_edge(shares(), WHERE, TEMPLATES)
    with pytest.raises(ConfigurationError, match="not the position of side"):
        check_edge(shares(position="short_shares"), WHERE, TEMPLATES)
    with pytest.raises(ConfigurationError, match="are for an option position"):
        check_edge(shares(book=True), WHERE, TEMPLATES)


def test_a_position_baseline_is_a_paired_base_not_a_screener() -> None:
    edge = parse_edge(document(baselines=["position:long_shares"]), "drift", WHERE)
    assert (edge.baselines, edge.position_baselines) == ((), ("long_shares",))
    check_edge(edge, WHERE, TEMPLATES)
    nope = parse_edge(document(baselines=["position:nothing"]), "drift", WHERE)
    with pytest.raises(ConfigurationError, match="baselines: no position template named"):
        check_edge(nope, WHERE, TEMPLATES)


def test_the_new_edge_keys_parse_and_a_document_without_them_hashes_as_before() -> None:
    plain = parse_edge(document(), "drift", WHERE)
    assert (plain.gate, plain.variant_grid, plain.verdict_profile) == (None, (), None)
    new = parse_edge(document(gate=GATE, verdict_profile="tails"), "drift", WHERE)
    assert new.gate is not None and new.verdict_profile == "tails"
    with pytest.raises(ConfigurationError, match="verdict_profile"):
        parse_edge(document(verdict_profile="best"), "drift", WHERE)
    keys = ("position", "gate", "verdict_profile", "variant_grid", "position_baselines")
    assert not set(keys) & set(identity_dict(asdict(plain)))
    assert "position" not in identity_dict(asdict(plain.outcome))


def test_the_sleeve_base_spec_checks_is_the_named_one() -> None:
    assert SLEEVE_BASE == DELTA_EQUIVALENT  # spec.py cannot import named.py (a cycle)


def test_a_grid_belongs_to_an_option_position_of_a_named_sleeve() -> None:
    grid = [{"prefix": "g", "strike_delta": [0.16, 0.2]}]
    sleeve = {**put(), "base": "delta_equivalent", "universe": NAMED, "variant_grid": grid}
    check_edge(parse_edge(sleeve, "drift", WHERE), WHERE, TEMPLATES)
    shares = document(variant_grid=grid)
    with pytest.raises(ConfigurationError, match="only an option_pnl position has a grid"):
        check_edge(parse_edge(shares, "drift", WHERE), WHERE, TEMPLATES)
    # a screened (cross-section) option setup: its harness does not read grid points yet
    with pytest.raises(ConfigurationError, match="only a named option sleeve"):
        check_edge(parse_edge({**put(), "variant_grid": grid}, "drift", WHERE), WHERE, TEMPLATES)
    clash = {**sleeve, "variants": [{"id": "g_d16"}]}
    with pytest.raises(ConfigurationError, match="clash with a variant"):
        check_edge(parse_edge(clash, "drift", WHERE), WHERE, TEMPLATES)


def test_a_gate_is_parsed_and_applied_so_the_edge_is_no_longer_refused() -> None:
    edge = parse_edge(document(gate=GATE), "drift", WHERE)
    check_edge(edge, WHERE, TEMPLATES)
    with pytest.raises(ConfigurationError, match="gate"):
        parse_edge(document(gate={"all": []}), "drift", WHERE)


def test_an_option_pnl_names_a_position_the_structure_enum_is_gone() -> None:
    old = {k: v for k, v in PUT.items() if k not in ("position", "expiry_cycle", "exit")}
    old |= {"structure": "put_short", "book": None, "skip_report_in_life": None}
    with pytest.raises(ConfigurationError, match="names a position template"):
        parse_edge(document(schedule="every_session", outcome={**old}), "drift", WHERE)
    nothing = {k: v for k, v in old.items() if k != "structure"}
    with pytest.raises(ConfigurationError, match="position: required for an option_pnl"):
        parse_edge(document(schedule="every_session", outcome=nothing), "drift", WHERE)


def test_a_position_is_refused_where_it_would_lose_a_leg_or_an_override() -> None:
    both = {**PUT, "kind": "excess_return", "benchmark": "SPY", "position": "long_shares",
            "side": "long_short"}  # fmt: skip
    for key in (
        "tenor_days",
        "strike_delta",
        "expiry_cycle",
        "skip_report_in_life",
        "book",
        "exit",
    ):
        both.pop(key)
    with pytest.raises(ConfigurationError, match="not the position of side"):
        check_edge(parse_edge(document(outcome=both, top_k=5), "drift", WHERE), WHERE, TEMPLATES)
    fly = parse_edge(put(position="iron_fly", exit=None), "drift", WHERE)
    with pytest.raises(ConfigurationError, match="has no leg chosen by delta"):
        check_edge(fly, WHERE, TEMPLATES)


# Site setups written with ADR 0088's keys from the start (no stored hash of theirs can change).
BORN_WITH_THE_KEYS = ("index_put_write",)


def test_every_site_edge_hashes_without_the_new_keys() -> None:
    new = ("position", "gate", "verdict_profile", "variant_grid", "position_baselines")
    edges = load_edges(FileConfigStore(REPO_ROOT / "config"))
    for edge in (e for e in edges if e.id not in BORN_WITH_THE_KEYS):
        assert not set(new) & set(identity_dict(asdict(edge))), edge.id
        assert "position" not in identity_dict(asdict(edge.outcome)), edge.id


SHARE_EXIT = {
    "kind": "excess_return", "horizon_sessions": [10], "benchmark": "SPY",
    "start_offset_sessions": 1, "position": "long_shares",
    "exit": {"take_profit": 0.1, "stop_loss": 0.05},
}  # fmt: skip


def shares(**changes: Any) -> Any:
    body = {k: v for k, v in {**SHARE_EXIT, **changes}.items() if v is not None}
    return document(outcome=body)


def test_a_shares_position_may_declare_take_profit_stop_loss_and_when_exits() -> None:
    """E3c-2b: the share path grain stores these, so the refusal is lifted: the settings are a
    move of the entry price (no credit), and the outcome reads the share path grain."""
    when = {"all": [{"field": "position.move_since_entry_pct", "op": "gte", "value": 0.2}]}
    for exit in ({"take_profit": 0.1}, {"stop_loss": 0.05}, {"when": when},
                 SHARE_EXIT["exit"]):  # fmt: skip
        edge = parse_edge(shares(exit=exit), "drift", WHERE)
        check_edge(edge, WHERE, TEMPLATES)
        assert reads_share_path(edge.outcome) and grain_name(edge.outcome) == "share_path"
    short = shares(position="short_shares", side="short", exit={"stop_loss": 0.05})
    check_edge(parse_edge({**short, "top_k": 5}, "drift", WHERE), WHERE, TEMPLATES)
    plain = parse_edge(shares(exit=None), "drift", WHERE)  # no exit: the price grain, as before
    assert not reads_share_path(plain.outcome) and grain_name(plain.outcome) == "stock"


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"exit": {"exit_dte": 21}}, "exit_dte"),
        ({"hold_rank": 8}, "hold_rank"),
        ({"measure": "residual_return"}, "a residual measure"),
        ({"kind": "hit_target", "measure": "excess_return", "direction": "above", "target": 0.1},
         "a hit_target outcome"),
        ({"side": "long_short"}, "a long_short outcome"),
        ({"position": "short_shares", "side": "short", "exit": {"take_profit": 0.1},
          "hold_rank": 8}, "hold_rank"),
    ],
)  # fmt: skip
def test_what_the_share_path_cannot_measure_is_refused_beside_an_exit(
    changes: dict[str, Any], match: str
) -> None:
    doc = shares(**changes)
    if {"hold_rank", "side"} & set(changes):
        doc = {**doc, "top_k": 5}
    with pytest.raises(ConfigurationError, match=match):
        check_edge(parse_edge(doc, "drift", WHERE), WHERE, TEMPLATES)


def test_a_share_path_has_one_benchmark_to_be_scored_against() -> None:
    """``benchmark = none`` is refused for an excess return at parse; the position check holds
    it too, for an outcome built another way (the path is scored against its benchmark's)."""
    edge = parse_edge(shares(), "drift", WHERE)
    bare = replace(edge, outcome=replace(edge.outcome, benchmark="none"))
    with pytest.raises(ConfigurationError, match="benchmark = none"):
        check_edge(bare, WHERE, TEMPLATES)


def test_a_take_profit_above_one_names_the_move_of_the_entry_price_for_shares() -> None:
    with pytest.raises(ConfigurationError, match="a favourable move of the entry price"):
        parse_edge(shares(exit={"take_profit": 1.5}), "drift", WHERE)


def test_a_time_series_base_or_a_position_baseline_is_refused_beside_a_share_exit() -> None:
    with pytest.raises(ConfigurationError, match="position:<template> values the picks"):
        edge = parse_edge({**shares(), "baselines": ["position:long_shares"]}, "drift", WHERE)
        check_edge(edge, WHERE, TEMPLATES)


def test_an_edge_and_its_variants_may_not_mix_share_path_and_price_outcomes() -> None:
    alone = {"kind": "hit_target", "measure": "excess_return", "direction": "above",
             "target": 0.05}  # another kind drops the position: the price grain  # fmt: skip
    mixed = {**shares(), "variants": [{"id": "alone", "outcome": alone}]}
    with pytest.raises(ConfigurationError, match="all read one outcome grain"):
        parse_edge(mixed, "drift", WHERE)
    both = {**shares(), "variants": [{"id": "tighter", "outcome": {"exit": {"stop_loss": 0.02}}}]}
    parse_edge(both, "drift", WHERE)  # two exits are two positions on one grain


def test_adding_an_exit_is_a_new_version_of_the_setup_not_of_its_profile() -> None:
    """E3c-2b versioning: ``position.exit`` is part of the outcome's identity, so the trial hash,
    the leg keys and the paper trades' ``outcome_hash`` change with it; the verdict profile (the
    rules that judge the setup, its return kind) does not."""
    plain = parse_edge(shares(exit=None), "drift", WHERE)
    held = parse_edge(shares(), "drift", WHERE)
    tighter = parse_edge(shares(exit={"take_profit": 0.1, "stop_loss": 0.04}), "drift", WHERE)
    assert len({outcome_hash(plain), outcome_hash(held), outcome_hash(tighter)}) == 3
    assert identity_dict(asdict(plain.outcome)) != identity_dict(asdict(held.outcome))
    assert plain.verdict_profile == held.verdict_profile


def test_the_exits_digest_names_the_declared_exits_and_only_them() -> None:
    """What the run records so the exit rule it publishes is the one it tested (ADR 0088 d19)."""
    spec = parse_edge(put(), "drift", WHERE).outcome.position
    assert spec is not None and exits_digest(spec) == exits_digest(spec)
    assert exits_digest(replace(spec, exit=ExitSettings(0.5, 3.0, 21))) != exits_digest(spec)
    assert exits_digest(replace(spec, book=False)) == exits_digest(spec)  # not an exit
    assert exits_digest(None) is None


def test_a_case_value_beside_a_share_exit_is_refused_until_its_points_are_read() -> None:
    """E13b resolves case values at D, but the share path reader selects the default point's rows
    only, so a case-valued share exit stays refused (never measured on its default alone)."""
    high_iv = {"all": [{"field": "rollup.iv_history@v2.iv_rank_252d", "op": "gte", "value": 0.8}]}
    exit = {"take_profit": {"cases": [{"when": high_iv, "value": 0.2}], "default": 0.1}}
    with pytest.raises(ConfigurationError, match="case values"):
        check_edge(parse_edge(shares(exit=exit), "drift", WHERE), WHERE, TEMPLATES)
