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
    "name": "The crash",
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
    assert found.by_key("tariffs_2025").name == "Tariff shock, spring 2025"
    assert found.by_key("tariffs_2025").recovered == date(2025, 6, 27)
    assert all(e.recovered is None or e.recovered > e.trough for e in found.episodes)
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
        ([changed(name=" ")], r"name: expected a non-empty string"),
        ([changed(recovered=date(2009, 3, 9))], r"recovered 2009-03-09 is not after the trough"),
        ([changed(recovered="2010-01-01")], r"recovered: expected a date"),
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


RECESSION: dict[str, Any] = {
    "start": date(2007, 12, 1),
    "end": date(2009, 6, 1),
    "announced_start": date(2008, 12, 1),
    "announced_end": date(2010, 9, 20),
}


def test_the_shipped_recessions_are_the_nber_chronology_since_1969() -> None:
    found = load_episodes(FileConfigStore(REPO_ROOT / "config")).recessions
    assert [(r.start.year, r.start.month) for r in found] == [
        (1969, 12), (1973, 11), (1980, 1), (1981, 7), (1990, 7), (2001, 3), (2007, 12), (2020, 2),
    ]  # fmt: skip
    assert found[0].announced_start is None  # NBER published no announcement before 1980
    assert found[-1].announced_end == date(2021, 7, 19)
    # Every recession episode overlaps one of the chronology's recessions
    episodes = load_episodes(FileConfigStore(REPO_ROOT / "config")).episodes
    starts = {(r.start, r.end) for r in found}
    assert all((e.nber_start, e.nber_end) in starts for e in episodes if e.recession)


def test_recessions_load_in_order() -> None:
    found = Episodes.from_document({"recession": [RECESSION]}).recessions
    assert found[0].announced_end == date(2010, 9, 20)
    plain = {"start": date(1969, 12, 1), "end": date(1970, 11, 1)}
    assert Episodes.from_document({"recession": [plain]}).recessions[0].announced_start is None


@pytest.mark.parametrize(
    ("recessions", "message"),
    [
        ([{**RECESSION, "end": date(2007, 12, 1)}], r"\[0\]: start .* not before end"),
        ([{**RECESSION, "announced_start": date(2007, 1, 1)}], r"announced_start is before"),
        ([{**RECESSION, "announced_end": date(2009, 1, 1)}], r"announced_end is before the end"),
        ([RECESSION, RECESSION], r"\[\[recession\]\]\[1\]: recessions must be in order"),
        ([{**RECESSION, "extra": 1}], r"unknown keys \['extra'\]"),
        ([{"start": date(2007, 12, 1)}], r"end: expected a date"),
    ],
)  # fmt: skip
def test_bad_recessions_fail_naming_the_recession(
    recessions: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        Episodes.from_document({"recession": recessions})
