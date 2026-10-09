"""The verdict thresholds: defaults are the owner's, a bad value names the file and key."""

import tomllib
from pathlib import Path

import pytest

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.core.model.errors import ConfigurationError


def test_defaults_are_the_owners_thresholds() -> None:
    d = VerdictSettings.from_document(None)
    assert (d.min_oos_trades, d.works_trades, d.works_oos_trades) == (40, 100, 40)
    assert (d.not_working_t, d.promising_t, d.works_t) == (1.0, 2.0, 3.0)
    assert (d.not_working_dsr, d.promising_dsr, d.works_dsr) == (0.5, 0.8, 0.95)
    assert (d.max_pbo, d.works_max_pbo, d.oos_lift_share) == (0.5, 0.2, 0.5)
    assert (d.forward_sessions, d.live_min_sessions, d.live_low, d.live_high) == (20, 10, 0.1, 0.9)


def test_a_document_overrides_and_an_unknown_key_fails() -> None:
    assert VerdictSettings.from_document({"min_oos_trades": 60}).min_oos_trades == 60
    with pytest.raises(ConfigurationError, match="unknown keys"):
        VerdictSettings.from_document({"min_trade": 1})
    with pytest.raises(ConfigurationError, match="max_pbo"):
        VerdictSettings.from_document({"max_pbo": 2})
    with pytest.raises(ConfigurationError, match="live_low"):
        VerdictSettings.from_document({"live_low": 1.5})


def test_the_committed_file_parses_to_the_defaults() -> None:
    doc = tomllib.loads(Path("config/site/verdict.toml").read_text())
    assert VerdictSettings.from_document(doc) == VerdictSettings()
