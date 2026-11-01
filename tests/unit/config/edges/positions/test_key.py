"""The position key (ADR 0088, G24): built from the resolved legs and parameters, never the
template's id; round-trips to its spec; two exit rules (or a different hold) are two keys; a
template edit changes the key a trade is stored under."""

from dataclasses import asdict, replace
from typing import Any

import pytest

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.identity import identity_dict
from algotrade.config.edges.positions.key import (
    key_of,
    parse_position_key,
    parsed_key,
    position_key,
    resolve_legs,
    with_legs,
)
from algotrade.config.edges.positions.templates import load_templates
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import WHERE, document

TEMPLATES = load_templates(FileConfigStore(REPO_ROOT / "config"))
PUT = {
    "kind": "option_pnl", "horizon_sessions": [21], "benchmark": "none",
    "start_offset_sessions": 1, "tenor_days": 30, "position": "put_spread", "strike_delta": 0.2,
    "expiry_cycle": "weekly", "exit": {"take_profit": 0.5, "stop_loss": 2.0},
}  # fmt: skip


def outcome(**changes: Any) -> Any:
    body = {k: v for k, v in {**PUT, **changes}.items() if v is not None}
    edge = parse_edge(document(schedule="every_session", outcome=body), "drift", WHERE)
    return with_legs(edge, TEMPLATES).outcome


def test_strike_delta_replaces_the_short_delta_leg_only_and_a_wing_keeps_its_delta() -> None:
    legs = outcome().position.legs
    assert [(leg.qty, leg.delta, leg.tenor_days) for leg in legs] == [(-1, 0.2, 30), (1, 0.1, 30)]
    plain = resolve_legs(outcome(strike_delta=None), TEMPLATES["put_spread"])
    assert [leg.delta for leg in plain] == [0.3, 0.1]


def test_the_key_round_trips_to_its_spec() -> None:
    o = outcome()
    key = position_key(o, 21)
    parsed = parse_position_key(key)
    assert parsed == parsed_key(o, 21) and key_of(parsed) == key
    assert parsed.hold == 21 and parsed.collateral == "max_loss" and parsed.offset == 1
    assert [x.kind for x in parsed.exits] == ["TAKE_PROFIT", "STOP_LOSS"]
    with pytest.raises(ConfigurationError, match="not a position key"):
        parse_position_key("{}")


def test_two_exit_rules_or_holds_are_two_keys() -> None:
    a = position_key(outcome(), 21)
    assert a != position_key(outcome(exit={"take_profit": 0.6, "stop_loss": 2.0}), 21)
    assert a != position_key(outcome(), 10)
    assert a == position_key(outcome(), 21)


def test_the_key_never_names_the_template_and_a_template_edit_changes_it() -> None:
    o = outcome()
    assert "put_spread" not in position_key(o, 21)
    spec = o.position
    wider = replace(
        TEMPLATES["put_spread"],
        legs=(
            TEMPLATES["put_spread"].legs[0],
            replace(TEMPLATES["put_spread"].legs[1], delta=0.05),
        ),
    )
    edited = replace(o, position=replace(spec, legs=resolve_legs(o, wider)))
    assert position_key(edited, 21) != position_key(o, 21)


def test_the_legs_the_loader_fills_are_not_part_of_an_edges_identity() -> None:
    body = {k: v for k, v in PUT.items() if v is not None}
    parsed = parse_edge(document(schedule="every_session", outcome=body), "drift", WHERE)
    loaded = with_legs(parsed, TEMPLATES)
    assert loaded.outcome.position.legs and not parsed.outcome.position.legs  # type: ignore[union-attr]
    assert identity_dict(asdict(loaded.outcome)) == identity_dict(asdict(parsed.outcome))
