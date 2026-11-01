"""The position of an outcome (ADR 0088, design 2.4, 2.4a): the ``position`` key with its option
parameters and ``[outcome.exit]`` round trip through ``parse_edge`` and are checked against the
site's templates where the edge loads; ``position`` with ``structure`` is refused, an entry at D's
close is refused, an edge that never names the keys hashes as before."""

from dataclasses import asdict
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.chain import grain_structure
from algotrade.config.edges.positions.spec import ExitSettings, PositionSpec, check_edge
from algotrade.config.edges.positions.templates import load_templates
from algotrade.core.model.errors import ConfigurationError
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
        ({"structure": "put_short"}, "not with structure"),
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


def test_a_grid_belongs_to_an_option_position() -> None:
    grid = [{"prefix": "g", "strike_delta": [0.16, 0.2]}]
    check_edge(parse_edge({**put(), "variant_grid": grid}, "drift", WHERE), WHERE, TEMPLATES)
    shares = document(variant_grid=grid)
    with pytest.raises(ConfigurationError, match="only an option_pnl position has a grid"):
        check_edge(parse_edge(shares, "drift", WHERE), WHERE, TEMPLATES)
    clash = {**put(), "variant_grid": grid, "variants": [{"id": "g_d16"}]}
    with pytest.raises(ConfigurationError, match="clash with a variant"):
        check_edge(parse_edge(clash, "drift", WHERE), WHERE, TEMPLATES)


def test_a_gate_is_parsed_but_refused_until_a_run_applies_it() -> None:
    edge = parse_edge(document(gate=GATE), "drift", WHERE)
    with pytest.raises(ConfigurationError, match="gate: not applied by any run yet"):
        check_edge(edge, WHERE, TEMPLATES)
    with pytest.raises(ConfigurationError, match="gate"):
        parse_edge(document(gate={"all": []}), "drift", WHERE)


def test_a_positioned_option_outcome_is_not_measured_as_another_structure() -> None:
    o = parse_edge(put(), "drift", WHERE).outcome
    with pytest.raises(ConfigurationError, match="not measured until the option engine"):
        grain_structure(o.structure or "", o.strike_delta)


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


def test_every_site_edge_hashes_without_the_new_keys() -> None:
    new = ("position", "gate", "verdict_profile", "variant_grid", "position_baselines")
    for edge in load_edges(FileConfigStore(REPO_ROOT / "config")):
        assert not set(new) & set(identity_dict(asdict(edge))), edge.id
        assert "position" not in identity_dict(asdict(edge.outcome)), edge.id
