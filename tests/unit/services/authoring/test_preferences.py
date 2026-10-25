"""``save_appearance``: the Light / Dark / System choice (ADR 0085) beside the views."""

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring import preferences
from algotrade.storage.configs.writer import MemoryConfigWriter

VIEW = {"columns": [], "decisions": ["WATCH"], "narrow_columns": []}


@pytest.mark.parametrize("theme", ["light", "dark", "system"])
def test_a_theme_is_saved(writer: MemoryConfigWriter, theme: str) -> None:
    assert preferences.save_appearance(writer, "local", theme) == theme
    assert writer.load("local", "preferences", "preferences") == {"appearance": {"theme": theme}}


@pytest.mark.parametrize("theme", ["", "Dark", "sepia", "auto"])
def test_another_value_is_refused_and_saves_nothing(writer: MemoryConfigWriter, theme: str) -> None:
    with pytest.raises(ConfigurationError, match=r"appearance\.theme"):
        preferences.save_appearance(writer, "local", theme)
    assert writer.load("local", "preferences", "preferences") is None


def test_the_views_are_kept_and_the_theme_survives_every_other_write(
    writer: MemoryConfigWriter,
) -> None:
    writer.save_preferences("local", {
        "views": {"screener:vrp": {"view": VIEW}},
        "screeners": {"vrp": {"view": VIEW}},  # the pre PR 8 layout: moved by any write
        "ideas": {"priority": ["vrp", "other"]},
    })  # fmt: skip
    preferences.save_appearance(writer, "local", "dark")
    saved = writer.load("local", "preferences", "preferences") or {}
    assert saved["appearance"] == {"theme": "dark"}
    assert saved["views"]["screener:vrp"]["view"] == VIEW and "screeners" not in saved
    preferences.save_view(writer, "local", "screener:vrp", [], None, ["QUALIFIED"])
    assert (writer.load("local", "preferences", "preferences") or {})["appearance"] == {
        "theme": "dark"
    }
    preferences.forget_screener(writer, "local", "other")
    after = writer.load("local", "preferences", "preferences") or {}
    assert after["appearance"] == {"theme": "dark"} and after["ideas"]["priority"] == ["vrp"]
    preferences.forget_screener(writer, "local", "vrp")
    after = writer.load("local", "preferences", "preferences") or {}
    assert after["appearance"] == {"theme": "dark"} and "screener:vrp" not in after["views"]
