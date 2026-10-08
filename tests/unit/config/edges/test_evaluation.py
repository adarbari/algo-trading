"""``EvaluationSettings``: the user's split over the site default, none (ADR 0015, ED5a)."""

from datetime import date

import pytest

from algotrade.config.edges.evaluation import EvaluationSettings, load_evaluation, parse_evaluation
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import MemoryConfigStore


def test_no_file_means_no_split_so_each_edges_frozen_from_is_the_site_split() -> None:
    assert load_evaluation(MemoryConfigStore({}), "alice") == EvaluationSettings(None)


def test_a_users_file_sets_the_split_and_the_site_user_has_none() -> None:
    configs = MemoryConfigStore(
        {("alice", "evaluation", "evaluation"): {"split_from": "2026-06-01"}}
    )
    assert load_evaluation(configs, "alice").split_from == date(2026, 6, 1)
    assert load_evaluation(configs, "bob").split_from is None
    assert load_evaluation(configs, "site").split_from is None


@pytest.mark.parametrize("doc", [{"split_from": "soon"}, {"split_from": 5}, {"split": "x"}])
def test_a_bad_value_or_unknown_key_names_the_file(doc: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError, match="users/alice/evaluation"):
        parse_evaluation(doc, "users/alice/evaluation.toml")
