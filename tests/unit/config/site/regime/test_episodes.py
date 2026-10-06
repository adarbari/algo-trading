"""``config/site/regime/episodes.toml`` (ADR 0047): the twelve shipped episodes load in order with
their dates and drawdowns, and every ordering and shape rule names the episode."""

from datetime import UTC, date, datetime
from typing import Any

import pytest

from algotrade.config.site.regime.episodes import Episodes, load_episodes
from algotrade.core.model.errors import ConfigurationError
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from tests.conftest import REPO_ROOT

EPISODE: dict[str, Any] = {
    "key": "crash",
    "peak": date(2007, 10, 9),
    "trough": date(2009, 3, 9),
    "spx_drawdown": -0.57,
    "nasdaq_drawdown": -0.56,
    "recession": True,
    "nber_start": date(2007, 12, 1),
    "nber_end": date(2009, 6, 1),
    "kind": "recession",
    "cause": "Housing and banks.",
    "known_from": date(2009, 3, 9),
    "notes": "Credit spreads first.",
}


def load(*episodes: dict[str, Any]) -> Episodes:
    return Episodes.from_document({"episode": list(episodes)})


def changed(**kw: Any) -> dict[str, Any]:
    return {**EPISODE, **kw}


def test_the_shipped_episodes_load() -> None:
    found = load_episodes(FileConfigStore(REPO_ROOT / "config"))
    assert len(found.episodes) == 12
    gfc = found.by_key("gfc_2007")
    assert (gfc.peak, gfc.trough, gfc.spx_drawdown) == (date(2007, 10, 9), date(2009, 3, 9), -0.57)
    assert gfc.recession and gfc.nber_start == date(2007, 12, 1)
    assert found.by_key("tariffs_2025").nber_start is None
    assert {e.known_from for e in found.episodes} == {e.trough for e in found.episodes}
    with pytest.raises(KeyError, match="no episode 'nope'"):
        found.by_key("nope")


def test_a_missing_file_has_no_episodes() -> None:
    assert load_episodes(MemoryConfigStore({})) == Episodes()


@pytest.mark.parametrize(
    ("episodes", "message"),
    [
        ([EPISODE, EPISODE], r"keys declared more than once: \['crash'\]"),
        ([changed(peak=date(2010, 1, 1))], r"\[\[episode\]\]\[0\]: peak 2010-01-01 is not before"),
        ([changed(known_from=date(2009, 1, 1))], r"known_from 2009-01-01 is before the trough"),
        ([changed(peak="2007-10-09")], r"peak: expected a date"),
        ([changed(peak=datetime(2007, 10, 9, 12, tzinfo=UTC))], r"peak: expected a date"),
        ([changed(spx_drawdown=0.2)], r"spx_drawdown: expected a fraction in \[-1, 0\]"),
        ([changed(nasdaq_drawdown=-1.5)], r"nasdaq_drawdown: expected a fraction"),
        ([changed(kind="crash")], r"kind: expected one of \['recession', 'shock'\]"),
        ([changed(cause=" ")], r"cause: expected a non-empty string"),
        ([changed(recession="yes")], r"recession: expected true or false"),
        ([changed(nber_end=None)], r"a recession episode names nber_start and nber_end"),
        ([changed(recession=False)], r"a recession episode names nber_start and nber_end"),
        ([changed(extra=1)], r"unknown keys \['extra'\]"),
    ],
)
def test_bad_episodes_fail_naming_the_episode(episodes: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load(*[{k: v for k, v in e.items() if v is not None} for e in episodes])


def test_the_document_shape_is_checked() -> None:
    with pytest.raises(ConfigurationError, match="episode: expected a list of tables"):
        Episodes.from_document({"episode": 1})
    with pytest.raises(ConfigurationError, match="unknown keys"):
        Episodes.from_document({"episodes": []})
