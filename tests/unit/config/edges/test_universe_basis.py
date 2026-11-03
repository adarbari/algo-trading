"""``UniverseBasisLimits``: the proposed defaults, the shipped ``verdict.toml`` section and the
validation of a changed one (ADR 0087 decision 6)."""

import tomllib
from pathlib import Path

import pytest

from algotrade.config.edges.universe_basis import UniverseBasisLimits
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.core.model.errors import ConfigurationError
from tests.conftest import REPO_ROOT

PROPOSED = UniverseBasisLimits(0.01, 0.98, 0.05, 0.05)


def test_the_defaults_are_the_proposed_values() -> None:
    assert UniverseBasisLimits() == PROPOSED
    assert UniverseBasisLimits.from_document(None) == PROPOSED


def test_the_shipped_section_says_the_same_and_the_verdict_loader_skips_it() -> None:
    doc = tomllib.loads(Path(REPO_ROOT / "config/site/verdict.toml").read_text())
    assert UniverseBasisLimits.from_document(doc) == PROPOSED
    VerdictSettings.from_document(doc)  # the section is typed apart: no "unknown keys" error


def test_a_section_is_read_and_a_bad_one_names_its_key() -> None:
    got = UniverseBasisLimits.from_document({"universe_basis": {"max_no_id_share": 0.02}})
    assert got.max_no_id_share == 0.02 and got.min_delisted_bars_share == 0.98
    with pytest.raises(ConfigurationError, match="min_delisted_bars_share"):
        UniverseBasisLimits.from_document({"universe_basis": {"min_delisted_bars_share": 1.5}})
    with pytest.raises(ConfigurationError, match="unknown keys"):
        UniverseBasisLimits.from_document({"universe_basis": {"nope": 1}})
