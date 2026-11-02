"""A setup whose rules read a fitted score keeps the sessions up to its bound in an in-sample
slice (E14): the slice flag the verdict never reads, the licence floor of decision 10's one
setting, and the cutoff the harness passes."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.edges.verdict import VerdictSettings
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.cross_section.detail.licences import (
    OPEN,
    PERSONAL,
    fitted_floor,
)
from algotrade.services.evaluation.cross_section.harness import _seen_until
from algotrade.services.evaluation.training.bound import scored
from tests.unit.services.evaluation.training.test_bound import _set

FROZEN = date(2026, 6, 1)


def _variant(impl: str) -> Any:
    return SimpleNamespace(config=SimpleNamespace(config=SimpleNamespace(impl=impl)))


def test_the_cutoff_is_the_later_of_the_frozen_period_and_the_score_bound() -> None:
    reads = scored(_set(), ["feature.edge_score_momo"])
    assert _seen_until(None, _variant("rules"), ()) is None
    bound = _seen_until(None, _variant("rules"), reads)
    assert bound is not None and bound > date(2026, 3, 3)
    assert (
        _seen_until(FROZEN, _variant("model"), reads) == FROZEN
    )  # a model screener keeps its stricter cutoff
    assert _seen_until(date(2026, 3, 1), _variant("model"), reads) == bound


def test_a_model_screener_without_frozen_from_stays_wholly_in_sample() -> None:
    reads = scored(_set(), ["feature.edge_score_momo"])
    assert _seen_until(None, _variant("model"), reads) is None  # never narrowed by the score


def test_the_floor_follows_the_one_setting() -> None:
    reads = scored(_set(), ["feature.edge_score_momo"])
    assert fitted_floor("owner_only", reads) == PERSONAL
    assert fitted_floor("forward_verdict", reads) == OPEN
    assert fitted_floor("owner_only", ()) == OPEN  # no score read: nothing changes


def test_the_setting_is_one_of_two_values_and_owner_only_by_default() -> None:
    assert VerdictSettings().fitted_score_setups == "owner_only"
    assert VerdictSettings.from_document({"fitted_score_setups": "forward_verdict"})
    with pytest.raises(ConfigurationError, match="owner_only"):
        VerdictSettings.from_document({"fitted_score_setups": "always"})
