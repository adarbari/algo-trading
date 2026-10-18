"""Rule-screen result frames: a screen with boolean groups is not stored until group rows land
(ADR 0071 PR 3), so member criteria are never written as gates."""

from datetime import UTC, date, datetime

import pytest

from algotrade.config.strategy.screen_spec import parse_screen_spec
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.views.feature_view import FeatureView
from algotrade.services.screening.rule_results import Stamp, rule_frames
from algotrade.strategies.screeners.rules import evaluate_screen

DAY = date(2026, 10, 2)
STAMP = Stamp(DAY, "run1", datetime(2026, 10, 2, tzinfo=UTC), "site", "s", "h", None)


def result(groups: dict[str, object]) -> object:
    criteria = {n: {"field": n, "op": "gt", "value": 1} for n in ("a", "b")}
    spec = parse_screen_spec("s", {"criteria": criteria, "groups": groups}, "s")
    return evaluate_screen(spec, FeatureView(DAY, {"EQ:X": {"a": 2, "b": 0}}))


def test_a_screen_with_groups_is_refused_by_both_frames() -> None:
    grouped = result({"g": {"any": ["a", "b"]}})
    with pytest.raises(ConfigurationError, match="ADR 0071 PR 3"):
        rule_frames(grouped, STAMP)  # type: ignore[arg-type]


def test_a_screen_without_groups_is_framed_as_before() -> None:
    frames = rule_frames(result({}), STAMP)  # type: ignore[arg-type]
    assert set(frames) == {"rule_screen", "rule_screen_values"}
