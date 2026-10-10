"""``leg_key``: every input moves it, and nothing but the inputs does."""

from dataclasses import replace

import pytest

from algotrade.config.strategy.schema import Group, Selection
from algotrade.services.evaluation.cross_section.legs import key
from algotrade.services.evaluation.cross_section.legs.key import leg_key, universe_hash

BASE = {
    "trial_hash": "t",
    "universe": "u",
    "iv_field": "feature.vrp_iv30",
    "event_class": None,
    "offset": 1,
    "draws": 1000,
    "expr_defs_hash": "e",
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


def test_the_universe_hash_follows_the_selection() -> None:
    selection = Selection("liquid", Group("all", ()), 50, "feature.x")
    assert universe_hash(selection) == universe_hash(replace(selection))
    assert universe_hash(replace(selection, max_instruments=60)) != universe_hash(selection)
    assert universe_hash(replace(selection, name="other")) != universe_hash(selection)
