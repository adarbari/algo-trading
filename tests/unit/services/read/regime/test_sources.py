"""``services/read/regime/sources.py``: a card's sources follow the catalogue's lineage to
``macro.toml`` series and ``[[source]]`` tables (every shipped card's leaves resolve to exactly
one source), and each series carries its provenance as the session knew it, read once per
publish."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.site.settings import load_macro
from algotrade.data.macro.series import stored_vintages
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.declaration import FeatureGroup, Input
from algotrade.features.framework.feature import Feature
from algotrade.services.features import catalogue
from algotrade.services.read.context import ReadContext
from algotrade.services.read.regime import sources
from algotrade.services.read.regime.sources import (
    activate,
    leaves,
    load_sources,
    series_of,
    table_source,
)
from algotrade.storage.configs.files import FileConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.conftest import REPO_ROOT
from tests.helpers.stored_frames import stamped
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with
from tests.unit.services.read.regime.conftest import _never

CONFIG = FileConfigStore(Path(REPO_ROOT / "config"))
SITE = catalogue(CONFIG)
CARDS = load_cards(CONFIG)
MACRO = load_macro(CONFIG)
INDICATORS = "market.regime_indicators@v1."


def names(key: str) -> tuple[str, str]:
    return (INDICATORS + key, f"{INDICATORS}{key}_on")


def test_every_shipped_cards_lineage_resolves_to_exactly_one_source_each() -> None:
    used: set[str] = set()
    for card in CARDS.cards:
        found = leaves(SITE, (card.feature, card.feature + "_on"))
        assert found, f"{card.key}: its feature is not in the catalogue"
        for leaf in found:
            matches = [m for m in (series_of(leaf, MACRO), table_source(leaf, CARDS.sources)) if m]
            assert len(matches) == 1, f"{card.key}: {leaf} resolves to {len(matches)} sources"
            used.add(leaf)
    unused = {s.input for s in CARDS.sources} - used
    assert not unused, f"[[source]] no card reaches: {sorted(unused)}"


def test_every_per_session_switch_names_a_catalogue_label_over_the_cards_own_inputs() -> None:
    switched = [c for c in CARDS.cards if c.source_by is not None]
    assert [c.key for c in switched] == ["spx_trend_200d"]
    for card in switched:
        assert card.source_by is not None
        selector = SITE.feature(card.source_by.feature)
        assert selector is not None, card.source_by.feature
        assert set(card.source_by.inputs) == set(selector.categories)
        governed = {i for inputs in card.source_by.inputs.values() for i in inputs}
        assert governed <= set(leaves(SITE, (card.feature, card.feature + "_on")))


def test_the_lineage_follows_inputs_through_features() -> None:
    # market_trend@v2: SPY's bars when their window is complete, else the SPX level
    spx = ("bars/1d", "instruments/symbol_ids", "series:SPX")
    assert leaves(SITE, names("spx_trend_200d")) == spx
    assert leaves(SITE, names("curve_10y3m")) == ("rates/treasury", "series:T10Y3M")
    assert leaves(SITE, names("sahm")) == ("series:UNRATE",)
    assert leaves(SITE, names("vix_term")) == ("series:VIX", "series:VIX3M")
    assert leaves(SITE, ("market.nope@v1.x",)) == ()  # not in the catalogue: no sources
    assert series_of("bars/1d", MACRO) is None and series_of("series:NOPE", MACRO) is None


def _trend_from_bars_or_index() -> FeatureSet:
    """The site's catalogue whose SPX trend reads SPY's bars or the SPX level by row (PR 230's
    ``market_trend@v2``), and an indicator over it."""
    inputs = ("bars/1d.close", "instruments/symbol_ids.instrument_id", "series:SPX")
    trend = FeatureGroup(
        "trend_both", 1, "test trend", (Input("bars/1d"),),
        (Feature("spx", "float32", "decimal", "SPX vs its 200-day mean", "no window",
                 inputs=inputs),),
        _never, entity="market",
    )  # fmt: skip
    card = FeatureGroup(
        "cards_both", 1, "test cards", (Input(trend.table),),
        (Feature("spx", "float32", "decimal", "the card", "null", inputs=("trend_both.spx@v1",)),),
        _never, entity="market",
    )  # fmt: skip
    return FeatureSet(
        {**SITE.code, trend.key: trend, card.key: card}, SITE.expressions, SITE.superseded
    )


def test_a_value_from_bars_or_an_index_level_shows_both_sources() -> None:
    ctx = replace(context(store_with()), features=_trend_from_bars_or_index())
    found = load_sources(ctx, {"spx": ("market.cards_both@v1.spx",)}, MACRO, CARDS.sources)
    spx = found["spx"]
    assert [s.label for s in spx] == [
        "Daily bars (Massive)",
        "Our ticker-to-id map (OpenFIGI)",
        "FRED SP500",
    ]
    assert (spx[0].series, spx[0].release_lag_days, spx[0].licence) == (None, None, "open")
    assert spx[2].series == "SPX" and spx[2].url == "https://fred.stlouisfed.org/series/SP500"
    assert (spx[2].licence, spx[2].release_lag_days) == ("personal", 1)
    assert spx[2].last_observation is None and spx[2].first_vintage is None  # nothing stored


def _row(iid: str, obs: date, vintage: date, kind: str) -> dict[str, object]:
    return {"instrument_id": iid, "series": iid.partition(":")[2], "obs_date": obs,
            "vintage_date": vintage, "value": 4.0, "vintage_kind": kind}  # fmt: skip


def _macro(writer: StoreWriter) -> None:
    rows = [
        _row("MACRO:UNRATE", date(1960, 1, 1), date(1964, 6, 1), "alfred"),  # first vintage
        _row("MACRO:UNRATE", date(2026, 7, 1), date(2026, 8, 7), "alfred"),
        _row("MACRO:UNRATE", date(2026, 8, 1), date(2026, 9, 5), "alfred"),  # newest known
        _row("MACRO:UNRATE", date(2026, 9, 1), date(2026, 10, 3), "alfred"),  # after D1
        _row("MACRO:BAMLH0A0HYM2", date(2026, 9, 30), date(2026, 10, 1), "lagged"),
    ]
    writer.write_table("macro/series", D1, "macro-1", stamped(rows, D1, "macro-1"))


def _cards(ctx: ReadContext) -> dict[str, tuple[sources.IndicatorSource, ...]]:
    lineage = {c.key: (c.feature, c.feature + "_on") for c in CARDS.cards}
    return load_sources(ctx, lineage, MACRO, CARDS.sources)


def test_each_series_carries_its_provenance_as_the_session_knew_it() -> None:
    found = _cards(replace(context(store_with(_macro)), features=SITE))
    [unrate] = found["unrate_trend"]
    assert (unrate.label, unrate.series, unrate.cadence) == ("FRED UNRATE", "UNRATE", "monthly")
    assert unrate.url == "https://fred.stlouisfed.org/series/UNRATE"
    assert (unrate.last_observation, unrate.vintage_date) == (date(2026, 8, 1), date(2026, 9, 5))
    assert unrate.vintage_kind == "alfred" and unrate.first_vintage == date(1964, 6, 1)
    assert unrate.terms and unrate.release_lag_days is not None
    [hy] = found["hy_oas"]
    assert (hy.last_observation, hy.vintage_kind) == (date(2026, 9, 30), "lagged")
    assert hy.first_vintage is None and hy.licence == "personal"  # unrevised: no ALFRED vintage
    curve = found["curve_10y3m"]
    assert [s.label for s in curve] == ["Treasury daily par yield curve", "FRED T10Y3M"]
    assert curve[1].last_observation is None  # nothing stored: no provenance, not an error
    breadth = found["breadth_200d"]
    assert [(s.label, s.url) for s in breadth] == [
        ("Our universe snapshot", None),
        ("Daily bars (Massive)", "https://massive.com/"),
    ]


def _late(writer: StoreWriter) -> None:
    rows = [_row("MACRO:UNRATE", date(2026, 8, 1), D1, "alfred")]  # first vintaged on D1
    writer.write_table("macro/series", D1, "macro-1", stamped(rows, D1, "macro-1"))


def test_a_vintage_after_the_session_is_not_known_then() -> None:
    ctx = replace(context(store_with(_late), D0), features=SITE)
    [unrate] = _cards(ctx)["unrate_trend"]
    assert (unrate.last_observation, unrate.first_vintage) == (None, None)
    [unrate] = _cards(replace(context(store_with(_late), D1), features=SITE))["unrate_trend"]
    assert (unrate.last_observation, unrate.first_vintage) == (date(2026, 8, 1), D1)


def test_the_vintages_are_read_once_per_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    real = stored_vintages

    def counting(reader: object, ids: tuple[str, ...]) -> object:
        calls.append(ids)
        return real(reader, ids)  # type: ignore[arg-type]

    monkeypatch.setattr(f"{sources.__name__}.stored_vintages", counting)
    ctx = replace(context(store_with(_macro)), features=SITE)
    first, again = _cards(ctx), _cards(ctx)
    assert first == again and len(calls) == 1
    assert "MACRO:UNRATE" in calls[0] and "IDX:VIX" in calls[0]


def test_a_publish_drops_the_cached_vintages() -> None:
    writers: list[StoreWriter] = []
    ctx = replace(context(store_with(_macro, writers.append)), features=SITE)
    [before] = _cards(ctx)["unrate_trend"]
    seq = ctx.reader.visible_seq()
    row = _row("MACRO:UNRATE", date(2026, 9, 1), date(2026, 9, 30), "alfred")
    frame = stamped([row], D1, "macro-2")
    writers[0].write_table("macro/series", D1, "macro-2", frame, pending=True)
    writers[0]._backend.tables.commit_run("macro-2", datetime(2026, 10, 2, tzinfo=UTC))
    assert ctx.reader.visible_seq() != seq  # the commit published
    [after] = _cards(ctx)["unrate_trend"]
    assert (before.last_observation, after.last_observation) == (date(2026, 8, 1), date(2026, 9, 1))


def test_only_the_sessions_source_of_a_switched_card_is_active() -> None:
    found = _cards(replace(context(store_with()), features=SITE))["spx_trend_200d"]
    switch = next(c.source_by for c in CARDS.cards if c.key == "spx_trend_200d")
    by_index = {s.input: s.active for s in activate(found, switch, "index")}
    assert by_index == {"bars/1d": False, "instruments/symbol_ids": False, "series:SPX": True}
    by_bars = {s.input: s.active for s in activate(found, switch, "bars")}
    assert by_bars == {"bars/1d": True, "instruments/symbol_ids": True, "series:SPX": False}
    assert not any(s.active for s in activate(found, switch, None))  # not stored: none fed it
    assert activate(found, None, None) == found and all(s.active for s in found)
