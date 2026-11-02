"""``leg_key``: every input moves it, and nothing but the inputs does."""

from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from algotrade.config.edges.verdict import OptionCosts
from algotrade.config.site.features.definitions import FeatureDefinition
from algotrade.config.strategy.schema import Group, Selection, parse_selection
from algotrade.services.evaluation.cross_section.legs import key
from algotrade.services.evaluation.cross_section.legs.key import leg_key, universe_hash
from algotrade.services.evaluation.cross_section.measuring import _RandomSpec, _Scope
from tests.unit.services.evaluation.cross_section.conftest import ACTIVE, edge
from tests.unit.services.evaluation.evidence.test_shapes import CHAIN

BASE = {
    "trial_hash": "t",
    "universe": "u",
    "iv_field": "feature.vrp_iv30",
    "event_class": None,
    "offset": 1,
    "draws": 1000,
    "expr_defs_hash": "e",
    "top_k": 5,
    "base": "event",
    "picks": "event",
    "cost_levels": (0.0, 15.0, 30.0, 50.0),
}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("trial_hash", "t2"),
        ("universe", "u2"),
        ("iv_field", "feature.other"),
        ("event_class", "earnings"),
        ("offset", 2),
        ("draws", 500),
        ("expr_defs_hash", "e2"),
        ("top_k", 6),
        ("base", "universe"),
        ("picks", "universe"),
        ("cost_levels", (0.0, 15.0, 30.0)),  # leg v2 counts hits at each level (ADR 0064)
    ],
)
def test_the_leg_key_changes_with_each_input(name: str, value: object) -> None:
    assert leg_key(**{**BASE, name: value}) != leg_key(**BASE)  # type: ignore[arg-type]


def test_the_leg_key_is_stable_and_follows_each_version(monkeypatch: pytest.MonkeyPatch) -> None:
    base = leg_key(**BASE)  # type: ignore[arg-type]
    assert base == leg_key(**BASE)  # type: ignore[arg-type]
    for version in ("LEG_VERSION", "HARNESS_VERSION", "SEED_VERSION"):
        monkeypatch.setattr(key, version, getattr(key, version) + 1)
        assert leg_key(**BASE) != base  # type: ignore[arg-type]
        monkeypatch.undo()


def test_leg_v5_is_a_new_key_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0088, E6a: a v4 leg (no trade-contract fields on its picks) is never reused: the key
    of fixed inputs is not the v4 one, and ``LEG_VERSION`` is 5."""
    assert key.LEG_VERSION == 5
    monkeypatch.setattr(key, "LEG_VERSION", 4)
    v4 = leg_key(**BASE)  # type: ignore[arg-type]
    monkeypatch.undo()
    assert leg_key(**BASE) != v4  # type: ignore[arg-type]


DRAW_KEY = "0d63c752da98a108fe3dcbd0a776618d03207c1d0c82e7e9ffe58afb98bc6e9f"


def test_the_draw_key_is_frozen_at_leg_version_4(monkeypatch: pytest.MonkeyPatch) -> None:
    """The draws are seeded by the key at ``DRAW_LEG_VERSION``: pinned, and a ``LEG_VERSION``
    bump (or any value) leaves it unchanged; only ``SEED_VERSION`` re-seeds."""
    assert key.DRAW_LEG_VERSION == 4
    draw = leg_key(**BASE, leg_version=key.DRAW_LEG_VERSION)  # type: ignore[arg-type]
    assert draw == DRAW_KEY
    monkeypatch.setattr(key, "LEG_VERSION", 99)
    assert leg_key(**BASE, leg_version=key.DRAW_LEG_VERSION) == DRAW_KEY  # type: ignore[arg-type]


def test_leg_v4_is_a_new_key_scheme() -> None:
    """ADR 0064 decision 4: a v1 leg (no picks, no hits per cost level) is never reused; ADR 0053
    amendment 2026-10-18: nor a v2 one (no sector-stratified draws), nor a v3 one (no buy/hold
    band)."""
    assert key.LEG_VERSION >= 4


def test_a_hold_rank_moves_the_key_only_when_set() -> None:
    """The band's names are in the leg, so its depth is in the key; an edge without one hashes
    as it did (``LEG_VERSION`` aside)."""
    plain = leg_key(**BASE)  # type: ignore[arg-type]
    assert leg_key(**BASE, hold_rank=None) == plain  # type: ignore[arg-type]
    assert leg_key(**BASE, hold_rank=8) != plain  # type: ignore[arg-type]
    assert leg_key(**BASE, hold_rank=8) != leg_key(**BASE, hold_rank=9)  # type: ignore[arg-type]


def test_the_universe_hash_follows_the_selection() -> None:
    selection = Selection("liquid", Group("all", ()), 50, "feature.x")
    assert universe_hash(selection) == universe_hash(replace(selection))
    assert universe_hash(replace(selection, max_instruments=60)) != universe_hash(selection)
    assert universe_hash(replace(selection, name="other")) != universe_hash(selection)


def test_the_expression_hash_ignores_prose_and_follows_the_formula() -> None:
    base = FeatureDefinition("x", "t", "a + b", "float", "pct", "text", "never")

    def hashed(definition: FeatureDefinition) -> str:
        found = SimpleNamespace(expressions={"x": SimpleNamespace(definition=definition)})
        return key.expression_hash(found)  # type: ignore[arg-type]

    prose = replace(base, description="reworded", null_meaning="other", unit="x", theme="u")
    assert hashed(prose) == hashed(base)
    assert hashed(replace(base, expr="a - b")) != hashed(base)
    assert hashed(replace(base, valid_range=(0.0, 1.0))) != hashed(base)


def _spec(costs: OptionCosts | None) -> _RandomSpec:
    return _RandomSpec(None, 1000, "e", "site", "edge", (0.0, 15.0), None, costs)


def test_option_costs_move_the_key_only_when_set_so_no_other_kinds_key_moves() -> None:
    """E6b-2: an option leg's values pay the commission, so its key holds ``[option_costs]``; an
    edge of every other kind passes none and hashes as it did."""
    plain = leg_key(**BASE)  # type: ignore[arg-type]
    costs = asdict(OptionCosts())
    assert leg_key(**BASE, option_costs=None) == plain  # type: ignore[arg-type]
    priced = leg_key(**BASE, option_costs=costs)  # type: ignore[arg-type]
    assert priced != plain
    assert priced == leg_key(**BASE, option_costs=dict(costs))  # type: ignore[arg-type]
    other = asdict(replace(OptionCosts(), commission_usd=1.0))
    assert leg_key(**BASE, option_costs=other) != priced  # type: ignore[arg-type]


def test_the_draw_key_ignores_the_option_costs_so_a_seed_never_moves_with_them() -> None:
    """A changed commission re-keys an option leg, never its random draws: the seed is the key at
    ``DRAW_LEG_VERSION`` without the costs (``_RandomSpec.draw_key_for``)."""
    spec = _spec(OptionCosts())
    scope = _Scope("main", edge(outcome=CHAIN), parse_selection(ACTIVE, "active"), "feature.x")
    variant = SimpleNamespace(id="v", hash="h", members=(), config=SimpleNamespace(hash="h"))
    cheaper = _spec(replace(OptionCosts(), commission_usd=0.0))
    assert spec.draw_key_for(scope, variant) == cheaper.draw_key_for(scope, variant)  # type: ignore[arg-type]
    assert spec.key_for(scope, variant) != cheaper.key_for(scope, variant)  # type: ignore[arg-type]
    share = _Scope("main", edge(), parse_selection(ACTIVE, "active"), "feature.x")
    assert _spec(OptionCosts()).key_for(share, variant) == _spec(None).key_for(share, variant)  # type: ignore[arg-type]
