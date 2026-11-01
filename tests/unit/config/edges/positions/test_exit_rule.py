"""``[exit_rule]`` of ``verdict.toml``: typed apart from ``VerdictSettings`` (it is not a judge
input), skipped by the verdict loader, so a document that carries it hashes as one without."""

import pytest

from algotrade.config.edges.positions.exit_rule import ExitRuleSettings
from algotrade.config.edges.verdict import VerdictSettings
from algotrade.core.model.errors import ConfigurationError


def test_the_section_types_and_a_file_without_it_has_none() -> None:
    doc = {"exit_rule": {"min_winners": 30}}
    assert ExitRuleSettings.from_document(doc) == ExitRuleSettings(30, 0.80, 2.0)
    assert (
        ExitRuleSettings.from_document({}) is None and ExitRuleSettings.from_document(None) is None
    )


@pytest.mark.parametrize(
    "section", [{}, {"min_winners": 0}, {"min_winners": 3, "stop_percentile": 1.5}, {"x": 1}]
)
def test_the_section_is_fail_closed(section: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        ExitRuleSettings.from_document({"exit_rule": section})


def test_the_verdict_loader_skips_the_section_and_its_settings_do_not_change() -> None:
    with_rule = VerdictSettings.from_document({"exit_rule": {"min_winners": 30}})
    assert with_rule == VerdictSettings.from_document({})
    assert "exit_rule" not in VerdictSettings.__dataclass_fields__
