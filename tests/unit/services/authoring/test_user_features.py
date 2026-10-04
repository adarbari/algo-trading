"""Save a named user feature: checked against the catalogue before the file changes."""

from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.user_features import save_user_feature
from algotrade.services.features import catalogue
from algotrade.storage.configs.writer import MemoryConfigWriter

HV_PCT: dict[str, Any] = {
    "expr": "price_stats.hv20 * 100",
    "dtype": "float",
    "unit": "pct_points",
    "description": "hv20 in percent",
    "null_meaning": "hv20 is null",
}


def test_saves_a_checked_feature(writer: MemoryConfigWriter) -> None:
    saved = save_user_feature(writer, "alice", "hv_pct", HV_PCT)
    assert (saved.field, saved.theme, saved.dtype) == ("feature.hv_pct", "builder", "float")
    assert saved.inputs == ("price_stats.hv20@v2",)
    assert "hv_pct" in catalogue(writer, "alice").expressions
    assert "hv_pct" not in catalogue(writer, "bob").expressions
    double = save_user_feature(writer, "alice", "hv_x2", HV_PCT | {"expr": "hv_pct * 2"})
    assert double.inputs  # a user feature may read the user's others
    assert set(writer.load("alice", "features", "builder") or {}) == {"hv_pct", "hv_x2"}


@pytest.mark.parametrize(
    ("name", "definition"),
    [
        ("bad", HV_PCT | {"expr": "nope.col * 2"}),
        ("bad", HV_PCT | {"expr": "price_stats.hv20 *"}),
        ("bad", HV_PCT | {"dtype": "str"}),
        ("bad", HV_PCT | {"materialise": True}),
        ("bad", {"expr": "price_stats.hv20"}),
        ("near_52w", HV_PCT),  # shadows a site feature
        ("../x", HV_PCT),
    ],
)
def test_fails_closed(writer: MemoryConfigWriter, name: str, definition: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError):
        save_user_feature(writer, "alice", name, definition)
    assert writer.names("alice", "features") == []


def test_one_name_lives_in_one_theme(writer: MemoryConfigWriter) -> None:
    save_user_feature(writer, "alice", "hv_pct", HV_PCT, theme="vol")
    with pytest.raises(ConfigurationError, match="vol"):
        save_user_feature(writer, "alice", "hv_pct", HV_PCT)
    with pytest.raises(ConfigurationError):
        save_user_feature(writer, "site", "hv_pct", HV_PCT)
