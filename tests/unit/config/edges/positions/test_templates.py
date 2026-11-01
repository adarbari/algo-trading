"""Position templates (ADR 0088, design 2.4): every shipped template parses; a template is typed
fail closed (no target-yield strike rule, a strike rule takes its own value, collateral fits the
legs); ``position_of`` names the template of a return outcome's side and of a ``position`` key,
and is None for a shape that is not one position; every site return edge maps to known
templates."""

from typing import Any

import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.positions.templates import (
    load_templates,
    parse_templates,
    position_of,
)
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import parse

SHIPPED = FileConfigStore(REPO_ROOT / "config")
OUTCOME = {"kind": "excess_return", "horizon_sessions": [20], "benchmark": "SPY",
           "start_offset_sessions": 1}  # fmt: skip
LEG = {"kind": "option", "right": "P", "qty": -1, "strike": "delta", "delta": 0.3}


def one(**changes: Any) -> dict[str, Any]:
    template = {"id": "t", "legs": [LEG], "collateral": "cash_secured", **changes}
    return {"template": [template]}


def test_every_shipped_template_parses() -> None:
    templates = load_templates(SHIPPED)
    assert {
        "long_shares", "short_shares", "short_put", "put_spread", "covered_call",
        "short_straddle", "iron_fly",
    } <= set(templates)  # fmt: skip
    assert templates["covered_call"].has_option and templates["long_shares"].share_only
    assert templates["put_spread"].legs[1].qty == 1


def test_a_missing_document_has_no_templates() -> None:
    assert load_templates(MemoryConfigStore({})) == {}


@pytest.mark.parametrize(
    ("doc", "match"),
    [
        (one(legs=[{**LEG, "strike": "yield"}]), "no target-yield strike rule"),
        (one(legs=[{**LEG, "strike": "atm"}]), "takes exactly its own value"),
        (one(legs=[{**LEG, "delta": 1.5}]), "delta: expected a fraction"),
        (one(legs=[{**LEG, "qty": 0}]), "qty"),
        (one(legs=[{"kind": "shares", "qty": 100, "right": "P"}]), "a shares leg has no"),
        (one(legs=[{"kind": "bond", "qty": 1}]), "kind"),
        (one(collateral="notional"), "does not fit these legs"),
        (one(legs=[{"kind": "shares", "qty": 100}]), "does not fit these legs"),
        (one(collateral="max_loss"), "does not fit these legs"),
        (one(collateral="margin"), "collateral"),
        (one(legs=[]), "legs"),
        ({"template": [one()["template"][0], one()["template"][0]]}, "listed twice"),
        ({"templates": []}, "unknown keys"),
    ],
)
def test_a_template_is_typed_fail_closed(doc: dict[str, Any], match: str) -> None:
    with pytest.raises(ConfigurationError, match=match):
        parse_templates(doc)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, ("long_shares",)),
        ({"side": "short", "top_k": 5}, ("short_shares",)),
        ({"side": "long_short", "top_k": 5}, ("long_shares", "short_shares")),
    ],
)
def test_position_of_maps_a_return_outcomes_side(
    changes: dict[str, Any], expected: tuple[str, ...]
) -> None:
    outcome = {**OUTCOME, "side": changes.get("side", "long")}
    extra = {"top_k": changes["top_k"]} if "top_k" in changes else {}
    assert position_of(parse(outcome=outcome, **extra).outcome) == expected


def test_position_of_is_none_for_a_shape_that_is_not_one_position() -> None:
    chain = {**OUTCOME, "kind": "option_model_pnl", "benchmark": "none", "horizon_sessions": [21],
             "structure": "atm_straddle_short", "iv_field": "feature.iv30"}  # fmt: skip
    assert position_of(parse(outcome=chain).outcome) is None


def test_every_site_return_edge_maps_to_known_templates() -> None:
    templates = load_templates(SHIPPED)
    seen = 0
    for edge in load_edges(SHIPPED):
        if edge.outcome.kind in ("excess_return", "hit_target"):
            ids = position_of(edge.outcome)
            assert ids is not None and set(ids) <= set(templates), edge.id
            seen += 1
    assert seen > 40
