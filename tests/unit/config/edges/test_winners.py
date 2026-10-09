"""``WinnersStudySettings``: the study's parameters, typed and validated (ADR 0053, ED6)."""

import copy
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.edges.winners import load_winners, parse_winners
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore

SITE_FILE = Path(__file__).parents[4] / "config/site/studies/winners.toml"


def _doc() -> dict[str, Any]:
    return tomllib.loads(SITE_FILE.read_text())


def test_the_site_file_parses_to_the_plan() -> None:
    s = load_winners(MemoryConfigStore({("site", "studies", "winners"): _doc()}))
    assert (s.horizon_sessions, s.benchmark, s.step_sessions) == (504, "SPY", 63)
    assert s.frozen_from == date(2026, 4, 1) and s.top_fraction == 0.02
    assert s.listing_age_edges_years == (2, 5) and s.min_clusters == 5


def test_a_missing_file_fails_closed() -> None:
    with pytest.raises(ConfigurationError, match="missing"):
        load_winners(MemoryConfigStore({}))


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("outcome", "horizon_sessions", 0),
        ("outcome", "horizons", 5),
        ("grid", "frozen_from", "2026-04-01"),
        ("winner", "top_fraction", 0),
        ("winner", "top_fraction", 1.5),
        ("controls", "listing_age_edges_years", [5, 2]),
        ("gate", "null_percentile", 100),
        ("discovery", "min_coverage", "high"),
    ],
)
def test_a_bad_value_or_unknown_key_names_the_file(section: str, key: str, value: object) -> None:
    doc = copy.deepcopy(_doc())
    doc[section][key] = value
    with pytest.raises(ConfigurationError, match=r"winners\.toml"):
        parse_winners(doc)
