"""Filters made on the fly from a catalogue feature (ADR 0082, "More filters"): the kind comes from
the dtype, a field the viewer's licences do not cover is neither offered, searchable nor accepted,
and the phrasebook's words are its synonyms."""

from itertools import pairwise

import pytest

from algotrade.config.filters.definitions import parse_filter_set
from algotrade.config.site.llm import Phrase
from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.services.licences import ALL_LICENCES, OPEN
from algotrade.services.read.context import open_stores
from algotrade.services.read.filtering.definitions import FilterRefusedError, ResolvedFilters
from algotrade.services.read.filtering.facets import compute_facets, nice_edges
from algotrade.services.read.filtering.feature_filters import (
    feature_definition,
    feature_filter_id,
    filterable_features,
    picked_feature_filters,
    requested_fields,
    takes_features,
)
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

FEATURES = open_stores(
    StoreReader(MemoryBackend()), FileConfigStore(REPO_ROOT / "config"), UserContext(SITE_USER)
).features
NUMBER = "rollup.volume@v1.dollar_volume"
PERSONAL = "rollup.ibkr_iv@v1.iv30_ibkr"


def test_a_number_is_a_range_a_flag_a_toggle_a_label_a_pick() -> None:
    kinds = {f.name: f.kind for f in filterable_features(FEATURES, ALL_LICENCES)}
    assert kinds[NUMBER] == "range"
    assert set(kinds.values()) <= {"range", "toggle", "pick"}
    assert {"range", "toggle", "pick"} <= set(kinds.values())
    definition = feature_definition(FEATURES, NUMBER)
    assert definition is not None
    assert (definition.id, definition.group, definition.guide) == (
        f"feature:{NUMBER}",
        "more",
        f"field:{NUMBER}",
    )


def test_an_unknown_field_or_a_reference_fact_makes_no_filter() -> None:
    assert feature_definition(FEATURES, "rollup.nope@v1.x") is None
    assert feature_definition(FEATURES, "instrument.symbol") is None


def test_a_field_the_licence_does_not_cover_is_not_searchable_and_is_withheld() -> None:
    open_names = {f.name for f in filterable_features(FEATURES, {OPEN})}
    assert NUMBER in open_names and PERSONAL not in open_names
    assert PERSONAL in {f.name for f in filterable_features(FEATURES, ALL_LICENCES)}
    on, off = picked_feature_filters(FEATURES, {OPEN}, [NUMBER, PERSONAL])
    assert [d.field for d in on] == [NUMBER] and [d.field for d in off] == [PERSONAL]


def test_the_phrasebook_words_are_the_synonyms_of_the_fields_they_name() -> None:
    phrases = [Phrase(say=("liquid", "easy to trade"), fields=(NUMBER,))]
    found = {f.name: f.synonyms for f in filterable_features(FEATURES, ALL_LICENCES, phrases)}
    assert found[NUMBER] == ("liquid", "easy to trade")
    assert found[PERSONAL] == ()


def test_only_a_surface_with_a_catalogue_field_takes_features() -> None:
    def surface(field: str):
        return parse_filter_set(
            "s",
            {
                "label": "S",
                "column": [{"id": "c", "dtype": "str", "source": "a.b"}],
                "filter": [{"id": "f", "label": "F", "group": "more", "kind": "pick",
                            "field": field, "options": "values", "guide": "term:t"}],
            },
        )  # fmt: skip

    assert takes_features(surface(NUMBER)) and not takes_features(surface("column:c"))


def test_the_ids_name_the_requested_fields_once() -> None:
    ids = [feature_filter_id(NUMBER), "decision", feature_filter_id(NUMBER)]
    assert requested_fields(ids) == (NUMBER,)


def test_an_input_for_a_feature_not_requested_is_refused() -> None:
    resolved = ResolvedFilters("s", ())
    with pytest.raises(FilterRefusedError):
        resolved.check([feature_filter_id(NUMBER)])


def test_a_made_range_gets_nice_edges_from_the_values() -> None:
    definition = feature_definition(FEATURES, NUMBER)
    assert definition is not None and definition.bins == ()
    column = [float(v) for v in (3, 14, 27, 41, 58, 99)]
    resolved = ResolvedFilters("s", (definition,))
    facets = compute_facets(
        {NUMBER: column}, len(column), resolved, [FilterInput(definition.id, [], 20.0, None)]
    )
    bins = facets.items[0].bins
    assert bins and bins[0].lo <= 3 and bins[-1].hi >= 99
    assert sum(b.count for b in bins) == 6  # a filter's histogram ignores its own mask
    assert facets.items[0].removes == 2 and facets.matched == 4


def test_nice_edges_are_steps_of_one_two_or_five_and_empty_without_a_spread() -> None:
    assert nice_edges([0.0, 100.0]) == tuple(float(v) for v in range(0, 101, 10))
    assert nice_edges([1.0, 1.0]) == ()
    tiny = nice_edges([1e-13, 5e-13])
    assert len(tiny) > 2 and all(a < b for a, b in pairwise(tiny))
    assert nice_edges([0.0, 0.7]) == tuple(round(k * 0.1, 12) for k in range(0, 8))


def test_a_fraction_is_shown_as_a_percent() -> None:
    returns = feature_definition(FEATURES, "rollup.price_stats@v2.ret_20d")
    assert returns is not None and returns.kind == "range" and returns.unit == "percent"
    assert feature_definition(FEATURES, NUMBER).unit is None  # type: ignore[union-attr]


def test_an_expression_over_a_personal_input_is_hidden_like_its_input() -> None:
    """``licence_of`` gives an expression the strictest licence of what it reads (ADR 0023)."""
    derived = [
        f.name
        for f in filterable_features(FEATURES, ALL_LICENCES)
        if f.name.startswith("feature.")
        and f.name not in {g.name for g in filterable_features(FEATURES, {OPEN})}
    ]
    assert derived, "the site has at least one formula over a personal-licence input"
    on, off = picked_feature_filters(FEATURES, {OPEN}, derived)
    assert not on and [d.field for d in off] == derived


def test_a_users_own_feature_name_is_not_a_site_field() -> None:
    assert feature_definition(FEATURES, "feature.draft_my_own_formula") is None
    assert picked_feature_filters(FEATURES, ALL_LICENCES, ["feature.draft_my_own_formula"]) == (
        (),
        (),
    )
