"""``IdeasRule``: the shipped file, defaults, failures that name the file, and the hash."""

import tomllib
from pathlib import Path

import pytest

from algotrade.config.ranking import ideas
from algotrade.config.ranking.ideas import IdeasRule, load_ideas_rule, parse_ideas_rule
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT


def test_the_shipped_file_is_the_owners_rule() -> None:
    rule = load_ideas_rule(FileConfigStore(REPO_ROOT / "config", local=False))
    assert (rule.site_top, rule.user_top, rule.user_weight) == (5, 20, 3)


def test_the_shipped_file_has_only_known_keys() -> None:
    doc = tomllib.loads((REPO_ROOT / "config" / "site" / "ranking" / "ideas.toml").read_text())
    assert parse_ideas_rule(doc) == IdeasRule()


def test_a_missing_file_is_the_default(tmp_path: Path) -> None:
    assert load_ideas_rule(FileConfigStore(tmp_path, local=False)) == IdeasRule()


@pytest.mark.parametrize(
    "doc",
    [{"site_top": 0}, {"user_weight": "3"}, {"user_top": 2.5}, {"top": 5}],
)
def test_a_bad_value_names_the_file(doc: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError, match=r"ideas\.toml"):
        parse_ideas_rule(doc)


def test_the_hash_moves_with_every_parameter_and_only_with_them() -> None:
    base = IdeasRule()
    assert base.hash == IdeasRule(5, 20, 3).hash
    assert len({base.hash, IdeasRule(6, 20, 3).hash, IdeasRule(5, 21, 3).hash,
                IdeasRule(5, 20, 4).hash}) == 4  # fmt: skip


def test_the_hash_moves_with_the_rule_code_version(monkeypatch: pytest.MonkeyPatch) -> None:
    before = IdeasRule().hash
    monkeypatch.setattr(ideas, "RULE_VERSION", ideas.RULE_VERSION + 1)
    assert IdeasRule().hash != before
