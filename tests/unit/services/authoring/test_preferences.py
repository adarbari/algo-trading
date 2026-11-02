"""``save_appearance``: the Light / Dark / System choice (ADR 0085) beside the views;
``save_watchlist`` and ``save_ideas_tab``: the trader site's stored choices (ADR 0083)."""

from typing import cast

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data.resolver import SymbolResolver
from algotrade.services.authoring import preferences
from algotrade.services.read.context import ReadContext
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


def ctx_knowing(monkeypatch: pytest.MonkeyPatch, ids: dict[str, str]) -> ReadContext:
    """A context whose reference snapshot lists ``ids`` (instrument id -> ticker)."""
    known = SymbolResolver(None, {t: i for i, t in ids.items()}, ids)
    monkeypatch.setattr(preferences, "resolver", lambda reader, on: known)
    session = type("Session", (), {"date": None})
    return cast(ReadContext, type("Ctx", (), {"reader": None, "session": session}))


def test_a_watchlist_is_saved_once_each_in_order_and_keeps_the_rest(
    writer: MemoryConfigWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = ctx_knowing(monkeypatch, {"EQ:A": "AAA", "EQ:B": "BBB"})
    preferences.save_appearance(writer, "local", "dark")
    assert preferences.save_watchlist(writer, "local", ["EQ:B", "EQ:A", "EQ:B"], ctx) == [
        "EQ:B",
        "EQ:A",
    ]
    saved = writer.load("local", "preferences", "preferences") or {}
    assert saved["watchlist"] == {"instruments": ["EQ:B", "EQ:A"]}
    assert saved["appearance"] == {"theme": "dark"}
    assert preferences.save_watchlist(writer, "local", [], ctx) == []


@pytest.mark.parametrize("bad", [["AAA"], ["EQ:A", "EQ:Z"], [""]])
def test_a_ticker_or_unknown_id_is_refused_and_saves_nothing(
    writer: MemoryConfigWriter, monkeypatch: pytest.MonkeyPatch, bad: list[str]
) -> None:
    ctx = ctx_knowing(monkeypatch, {"EQ:A": "AAA", "EQ:B": "BBB"})
    with pytest.raises(ConfigurationError, match=r"watchlist\.instruments"):
        preferences.save_watchlist(writer, "local", bad, ctx)
    assert writer.load("local", "preferences", "preferences") is None


def test_more_than_fifty_instruments_are_refused(
    writer: MemoryConfigWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = {f"EQ:{n}": f"S{n}" for n in range(51)}
    many = ctx_knowing(monkeypatch, ids)
    with pytest.raises(ConfigurationError, match="at most 50"):
        preferences.save_watchlist(writer, "local", list(ids), many)
    assert preferences.save_watchlist(writer, "local", list(ids)[:50], many) == list(ids)[:50]


def test_the_default_tab_is_saved_and_keeps_the_retired_priority(
    writer: MemoryConfigWriter,
) -> None:
    writer.save_preferences("local", {"ideas": {"priority": ["vrp"]}})
    assert preferences.save_ideas_tab(writer, "local", "premium") == "premium"
    saved = writer.load("local", "preferences", "preferences") or {}
    assert saved["ideas"] == {"priority": ["vrp"], "default_tab": "premium"}


@pytest.mark.parametrize("tab", ["", "Stocks", "options", "yours"])
def test_another_tab_is_refused(writer: MemoryConfigWriter, tab: str) -> None:
    with pytest.raises(ConfigurationError, match=r"ideas\.default_tab"):
        preferences.save_ideas_tab(writer, "local", tab)
    assert writer.load("local", "preferences", "preferences") is None


def test_a_saved_id_the_snapshot_dropped_never_blocks_the_next_edit(
    writer: MemoryConfigWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    both = ctx_knowing(monkeypatch, {"EQ:A": "AAA", "EQ:B": "BBB"})
    preferences.save_watchlist(writer, "local", ["EQ:A", "EQ:B"], both)
    later = ctx_knowing(monkeypatch, {"EQ:A": "AAA", "EQ:C": "CCC"})  # B was delisted
    assert preferences.save_watchlist(writer, "local", ["EQ:A", "EQ:B", "EQ:C"], later) == [
        "EQ:A",
        "EQ:B",
        "EQ:C",
    ]
    with pytest.raises(ConfigurationError, match="EQ:Z"):  # a new unknown id is still refused
        preferences.save_watchlist(writer, "local", ["EQ:A", "EQ:Z"], later)
    assert preferences.save_watchlist(writer, "local", ["EQ:A"], later) == ["EQ:A"]
