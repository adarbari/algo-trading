"""Save a user's train / test split: a stored session or none, only in the user's own file."""

from datetime import date

import pytest

from algotrade.config.edges.evaluation import load_evaluation
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.evaluation import save_split
from algotrade.storage.configs.writer import MemoryConfigWriter

LATEST = date(2026, 9, 30)


def test_saves_and_clears_the_split_for_that_user_only(writer: MemoryConfigWriter) -> None:
    saved = save_split(writer, "alice", date(2026, 4, 1), LATEST)
    assert saved.split_from == date(2026, 4, 1)
    assert load_evaluation(writer, "alice").split_from == date(2026, 4, 1)
    assert load_evaluation(writer, "bob").split_from is None
    assert save_split(writer, "alice", None, LATEST).split_from is None
    assert load_evaluation(writer, "alice").split_from is None


@pytest.mark.parametrize(
    "split",
    [date(2026, 10, 1), date(1999, 12, 31), date(2026, 4, 4), date(2026, 4, 3), date(2026, 7, 3)],
)
def test_a_date_outside_the_stored_range_is_refused_and_nothing_is_written(
    writer: MemoryConfigWriter, split: date
) -> None:
    with pytest.raises(ConfigurationError, match="trading session"):
        save_split(writer, "alice", split, LATEST)
    assert writer.load("alice", "evaluation", "evaluation") is None


def test_the_site_is_never_written(writer: MemoryConfigWriter) -> None:
    with pytest.raises(ConfigurationError, match="site"):
        save_split(writer, "site", date(2026, 4, 1), LATEST)
    assert writer.load("site", "evaluation", "evaluation") is None
