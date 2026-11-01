"""The stored default tab and watchlist: valid, missing, malformed. A context without a session
reads the ids and no tickers."""

from typing import Any, cast

import pytest

from algotrade.config.user import UserContext
from algotrade.services.read.context import Stores
from algotrade.services.read.users.trader import (
    MAX_WATCHLIST,
    TraderPreferences,
    WatchedInstrument,
    load_trader_preferences,
)
from algotrade.storage.configs.files import MemoryConfigStore


def ctx_of(document: Any) -> Stores:
    docs = {} if document is None else {("me", "preferences", "preferences"): document}
    fields = {"configs": MemoryConfigStore(docs), "user": UserContext("me")}
    return cast(Stores, type("Ctx", (), fields))


def test_a_stored_tab_and_watchlist_are_read_in_order() -> None:
    doc = {"ideas": {"default_tab": "premium"}, "watchlist": {"instruments": ["EQ:B", "EQ:A"]}}
    assert load_trader_preferences(ctx_of(doc)) == TraderPreferences(
        "premium", (WatchedInstrument("EQ:B", None), WatchedInstrument("EQ:A", None))
    )


@pytest.mark.parametrize(
    "document",
    [
        None,
        {},
        {"ideas": {"priority": ["vrp"]}},
        {"ideas": {"default_tab": "Stocks"}},
        {"ideas": {"default_tab": 3}},
        {"ideas": "stocks", "watchlist": "EQ:A"},
        {"watchlist": {"instruments": "EQ:A"}},
    ],
)
def test_a_missing_or_malformed_choice_reads_as_absent(document: Any) -> None:
    assert load_trader_preferences(ctx_of(document)) == TraderPreferences(None, ())


def test_repeats_and_non_strings_are_dropped_and_the_list_is_capped() -> None:
    ids = [f"EQ:{n}" for n in range(MAX_WATCHLIST + 5)]
    doc = {"watchlist": {"instruments": ["EQ:0", 7, *ids]}}
    got = load_trader_preferences(ctx_of(doc)).watchlist
    assert [w.instrument_id for w in got] == ids[:MAX_WATCHLIST]
