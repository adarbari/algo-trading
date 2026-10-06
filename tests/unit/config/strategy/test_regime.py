"""``[regime]`` (ADR 0049): typed, validated with its path, layered per ADR 0015 and hashed."""

from typing import Any

import pytest

from algotrade.config.strategy.regime import (
    DEFAULT_MULTIPLIERS,
    REGIME_LABEL,
    RegimeSettings,
    site_regime,
)
from algotrade.config.strategy.resolve import resolve
from algotrade.config.user import SITE_USER, UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT

ACTIVE = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}
SITE_REGIME = {
    "enabled": False,
    "multipliers": {"STRESS": 0.4},
    "screeners": {"vrp_scanner": {"pause_in": ["STRESS", "CRISIS"]}},
}


def store(
    user: dict[str, Any] | None = None,
    site: dict[str, Any] | None = None,
    extra: dict[tuple[str, str, str], Any] | None = None,
) -> MemoryConfigStore:
    docs: dict[tuple[str, str, str], Any] = {
        ("site", "defaults", "defaults"): {"regime": SITE_REGIME},
        ("site", "strategies", "vrp_scanner"): {
            "id": "vrp_scanner",
            "kind": "strategy",
            "impl": "buy_and_hold",
            "selection": {"name": "all", "where": {"all": [ACTIVE]}},
            **(site or {}),
        },
    }
    if user is not None:
        docs[("u1", "strategies", "vrp_scanner")] = user
    docs.update(extra or {})
    return MemoryConfigStore(docs)


def test_defaults_are_off_and_fail_closed() -> None:
    d = RegimeSettings.parse(None, "x [regime]")
    assert not d.enabled and d.label == REGIME_LABEL == "market.regime@v2.label"
    assert dict(d.multipliers) == dict(DEFAULT_MULTIPLIERS)
    assert d.unknown_multiplier == 0.0 and d.pause_in == frozenset()
    assert d.pauses_for("anything") == frozenset()


def test_site_default_then_user_override_then_run() -> None:
    resolved = resolve("vrp_scanner", UserContext(SITE_USER), store().load)
    site = resolved.regime
    assert not site.enabled
    assert site.multipliers["STRESS"] == 0.4 and site.multipliers["CALM"] == 1.0
    assert site.pauses_for("vrp_scanner") == {"STRESS", "CRISIS"}

    user = store(
        {"regime": {"enabled": True, "multipliers": {"CRISIS": 0.0}, "pause_in": ["CRISIS"]}}
    )
    mine = resolve("vrp_scanner", UserContext("u1"), user.load)
    assert mine.regime.enabled and mine.regime.multipliers["CRISIS"] == 0.0
    assert mine.regime.multipliers["STRESS"] == 0.4  # tables merge: the site value stays
    assert mine.regime.pause_in == {"CRISIS"}
    assert mine.layers[-1] == "u1/strategies/vrp_scanner"

    run = resolve("vrp_scanner", UserContext("u1"), user.load, {"regime": {"enabled": False}})
    assert not run.regime.enabled
    assert len({resolved.hash, mine.hash, run.hash}) == 3  # the hash records [regime]


@pytest.mark.parametrize(
    ("regime", "message"),
    [
        ({"multipliers": {"STRESS": 1.5}}, r"\[regime.multipliers\] STRESS: expected a fraction"),
        ({"multipliers": {"STORM": 0.5}}, r"\[regime.multipliers\]: unknown keys \['STORM'\]"),
        ({"pause_in": ["STORM"]}, r"\[regime\] pause_in: unknown labels \['STORM'\]"),
        ({"pause_in": "STRESS"}, r"pause_in: expected a list of strings"),
        ({"unknown_multiplier": -1}, r"unknown_multiplier: expected a number >= 0"),
        ({"label": "rollup.iv30@v1.iv30"}, r"label: expected a market feature field"),
        ({"label": "nonsense"}, r"label: expected a market feature field"),
        ({"enabled": "yes"}, r"enabled: expected true or false"),
        ({"screeners": {"vrp_scanner": {"size": 1}}}, r"\[regime.screeners.vrp_scanner\]: unknown"),
        ({"screeners": {"vrp_scanner": {"pause_in": ["X"]}}}, r"unknown labels \['X'\]"),
        ({"max_regime": "STRESS"}, r"\[regime\]: unknown keys \['max_regime'\]"),
    ],
)
def test_bad_values_fail_at_resolve_with_their_path(regime: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        resolve("vrp_scanner", UserContext(SITE_USER), store(site={"regime": regime}).load)


def test_the_committed_site_defaults_pause_the_vrp_scanner_in_storms() -> None:
    regime = site_regime(open_config_store(str(REPO_ROOT / "config")).load)
    assert not regime.enabled and regime.label == REGIME_LABEL
    assert dict(regime.multipliers) == dict(DEFAULT_MULTIPLIERS)
    assert regime.pauses_for("vrp_scanner") == {"STRESS", "CRISIS"}
    assert regime.pauses_for("short_premium_liquidity") == frozenset()


MY_VRP = ("u1", "strategies", "my_vrp")


def test_a_users_copy_keeps_the_presets_pause() -> None:
    """A user's ``my_vrp`` extending ``vrp_scanner`` pauses where the preset does, unless
    ``[regime.screeners.my_vrp]`` says otherwise."""
    copy = {"id": "my_vrp", "extends": "vrp_scanner"}
    mine = resolve("my_vrp", UserContext("u1"), store(extra={MY_VRP: copy}).load)
    assert mine.preset == "vrp_scanner" and mine.config.id == "my_vrp"
    assert mine.gate_pauses == {"STRESS", "CRISIS"}
    own = {**copy, "regime": {"screeners": {"my_vrp": {"pause_in": ["CRISIS"]}}}}
    assert resolve("my_vrp", UserContext("u1"), store(extra={MY_VRP: own}).load).gate_pauses == {
        "CRISIS"
    }
    site = resolve("vrp_scanner", UserContext(SITE_USER), store().load)
    assert site.preset == "vrp_scanner" and site.gate_pauses == {"STRESS", "CRISIS"}
    assert RegimeSettings(pause_in=frozenset({"STRESS"})).pauses_for("x", "y") == {"STRESS"}
