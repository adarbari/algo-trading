"""The structured phrasebook entries against the real catalogue: every shipped one names a
catalogue field, an op that fits its type and values among its categories (units are the
catalogue's: fractions where the field is a fraction)."""

import pytest

from algotrade.config.site.drafting.criteria import PhraseCriterion
from algotrade.config.site.llm import Phrase
from algotrade.config.site.settings import load_phrasebook
from algotrade.config.user import UserContext
from algotrade.services.drafting.phrasebook.check import (
    criterion_problem,
    phrase_criteria,
    problems,
)
from algotrade.services.drafting.phrasebook.resolve import is_structured
from algotrade.services.read.context import open_context
from algotrade.services.read.instruments.catalogue import FeatureInfo, feature_infos
from algotrade.storage.factory import open_config_store
from tests.conftest import REPO_ROOT
from tests.unit.services.drafting.test_screens import ALICE, DAY, seeded


@pytest.fixture(scope="module")
def site() -> tuple[dict[str, FeatureInfo], tuple[Phrase, ...]]:
    reader, _ = seeded()
    store = open_config_store(REPO_ROOT / "config")
    ctx = open_context(reader, store, UserContext(ALICE), DAY)
    return dict(feature_infos(ctx.features)), load_phrasebook(store).phrases


def test_every_structured_entry_passes_against_the_catalogue(site) -> None:
    infos, book = site
    assert problems(book, infos) == []


def test_enough_entries_are_structured_and_every_one_keeps_its_hint(site) -> None:
    _, book = site
    structured = [p for p in book if is_structured(p)]
    assert 15 <= len(structured) <= 40
    assert all(p.hint for p in structured)
    for p in structured:  # the structured fields are among the entry's own fields
        assert {c.field for c in phrase_criteria(p)} <= set(p.fields)


def test_the_liquid_entry_has_three_readings_and_a_default(site) -> None:
    _, book = site
    (liquid,) = [p for p in book if "liquid" in p.say]
    assert len(liquid.alternatives) == 3
    assert liquid.alternatives[liquid.default_index].label == "$50M a day"


@pytest.mark.parametrize(
    ("criterion", "message"),
    [
        (PhraseCriterion("feature.nope", "eq", 1), "not in the catalogue"),
        (PhraseCriterion("feature.trend_state", "gt", 1), "needs a number field"),
        (PhraseCriterion("feature.trend_state", "eq", "SIDEWAYS_X"), "not among"),
        (PhraseCriterion("feature.trend_state", "eq", 1), "takes text"),
        (PhraseCriterion("feature.breakout_20d", "eq", "yes"), "boolean"),
        (PhraseCriterion("feature.atr_pct", "eq", "high"), "does not fit a number"),
    ],
)
def test_a_criterion_the_catalogue_refuses_says_why(site, criterion, message) -> None:
    infos, _ = site
    assert message in (criterion_problem(criterion, infos) or "")


@pytest.mark.parametrize(
    ("criterion", "text", "message"),
    [
        (PhraseCriterion("feature.atr_pct", "gte", 3), "", "not a fraction"),  # 3%, written 3
        (PhraseCriterion("feature.iv_rank", "gte", 50), "", "outside the field's range"),
        (PhraseCriterion("rollup.momentum@v1.rsi_14", "lt", 130), "", "outside the field's range"),
        (PhraseCriterion("feature.pct_from_high_52w", "gte", 0.1), "", "outside the field's range"),
        (PhraseCriterion("rollup.momentum@v1.rsi_14", "lt", 0.3), "30%", "percentage points"),
    ],
)
def test_an_impossible_magnitude_is_refused(site, criterion, text, message) -> None:
    infos, _ = site
    assert message in (criterion_problem(criterion, infos, text) or "")


def test_a_small_percentage_points_value_passes_without_a_percent_in_the_text(site) -> None:
    infos, _ = site
    assert criterion_problem(PhraseCriterion("rollup.momentum@v1.rsi_14", "lt", 0.3), infos) is None
