"""``load_regime_episodes`` (ADR 0047): the reference episodes and NBER recessions the session
knew, from ``config/site/regime/episodes.toml``: an episode from its trough, its recovery only
once it has come, a recession from the day the committee dated its peak and its end from the
day it dated the trough (the month itself where NBER published no date)."""

from dataclasses import replace
from datetime import date
from typing import Any

from algotrade.services.read.regime.episodes import Recession, RegimeEpisodes, load_regime_episodes
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.instruments.conftest import D1, context, store_with

EPISODE: dict[str, Any] = {
    "key": "gfc", "name": "The crash", "peak": date(2007, 10, 9), "trough": date(2009, 3, 9),
    "recovered": date(2013, 3, 28), "spx_drawdown": -0.57, "nasdaq_drawdown": -0.56,
    "recession": True, "nber_start": date(2007, 12, 1), "nber_end": date(2009, 6, 1),
    "kind": "recession", "cause": "Banks.", "known_from": date(2009, 3, 9), "notes": "Spreads.",
}  # fmt: skip
LATER = {**EPISODE, "key": "later", "peak": date(2015, 1, 1), "trough": date(2016, 1, 20),
         "known_from": date(2016, 1, 20), "recovered": None, "recession": False,
         "kind": "shock", "nber_start": None, "nber_end": None}  # fmt: skip
GFC = {"start": date(2007, 12, 1), "end": date(2009, 6, 1),
       "announced_start": date(2008, 12, 1), "announced_end": date(2010, 9, 20)}  # fmt: skip
OLD = {"start": date(1973, 11, 1), "end": date(1975, 3, 1)}


def known(day: date, episodes: list[dict[str, Any]], recessions: list[dict[str, Any]]) -> Any:
    def drop(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in r.items() if v is not None} for r in rows]

    docs = {("site", "regime", "episodes"): {"episode": drop(episodes), "recession": recessions}}
    ctx = context(store_with(), D1)
    session = replace(ctx.session, date=day)
    return load_regime_episodes(replace(ctx, session=session, configs=MemoryConfigStore(docs)))


def test_an_episode_is_listed_from_its_trough_and_recovered_only_once_it_has_come() -> None:
    assert known(date(2009, 3, 8), [EPISODE], []).episodes == ()  # the trough is not in yet
    during = known(date(2009, 3, 9), [EPISODE, LATER], []).episodes
    assert [e.key for e in during] == ["gfc"] and during[0].recovered is None
    assert during[0].name == "The crash" and during[0].spx_drawdown == -0.57
    assert known(date(2013, 3, 27), [EPISODE], []).episodes[0].recovered is None
    assert known(date(2013, 3, 28), [EPISODE], []).episodes[0].recovered == date(2013, 3, 28)
    late = known(date(2020, 1, 1), [EPISODE, LATER], []).episodes
    assert [e.key for e in late] == ["gfc", "later"]  # file order
    assert late[1].recovered is None  # never recovered in the file


def test_a_recession_is_known_from_its_announcement_and_ends_when_announced() -> None:
    assert known(date(2008, 11, 30), [], [GFC]).recessions == ()  # in it, not yet dated
    ongoing = known(date(2008, 12, 1), [], [GFC]).recessions
    # the session does not know the end, nor when it will be announced
    assert ongoing == (Recession(date(2007, 12, 1), None, date(2008, 12, 1), None),)
    assert known(date(2010, 9, 19), [], [GFC]).recessions[0].end is None  # trough past, undated
    over = known(date(2010, 9, 20), [], [GFC]).recessions[0]
    assert (over.end, over.announced_end) == (date(2009, 6, 1), date(2010, 9, 20))


def test_a_recession_with_no_published_announcement_is_known_from_its_own_months() -> None:
    assert known(date(1973, 10, 31), [], [OLD]).recessions == ()
    mid = known(date(1974, 6, 1), [], [OLD]).recessions[0]
    assert (mid.start, mid.end, mid.announced_start) == (date(1973, 11, 1), None, None)
    done = known(date(1975, 3, 1), [], [OLD]).recessions[0]
    assert (done.end, done.announced_end) == (date(1975, 3, 1), None)


def test_without_the_file_there_is_nothing() -> None:
    ctx = replace(context(store_with()), configs=MemoryConfigStore({}))
    assert load_regime_episodes(ctx) == RegimeEpisodes((), ())
