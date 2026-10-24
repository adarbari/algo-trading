"""A filter whose field has no known value for the read session is withheld (NOT_STORED, the
Guide term ``filter_withheld_no_data``), one with some known value is offered, an empty
population withholds nothing, a licence withholding stays LICENCE, and an input naming a
withheld filter is ignored, never refused (decision log 2026-10-24)."""

import copy

import pytest

from algotrade.data import StoreReader
from algotrade.services.read.availability.cause import UnavailableKind
from algotrade.services.read.context import ReadContext
from algotrade.services.read.filtering import no_data
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.filtering.served import NO_DATA_TERM, load_served_filters
from algotrade.services.read.screens.ideas import load_ideas
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.unit.services.read.screens.conftest import D1, IDEAS_FILTERS, context, screens_store

USERS = {
    "user": [
        {"id": "admin", "role": "admin"},
        {"id": "bare", "role": "trader"},
        {"id": "full", "role": "trader", "licences": ["personal", "yahoo"]},
    ]
}
IV = "rollup.ibkr_iv@v1.iv30_ibkr"
IV_FILTER = {
    "id": "iv", "label": "IV", "group": "tradeable", "kind": "range", "field": IV,
    "bins": [0, 0.5, 1], "guide": "term:filter_spread",
}  # fmt: skip
DOCS = {
    ("site", "settings", "users"): USERS,
    ("site", "filters", "ideas"): {**IDEAS_FILTERS, "filter": [*IDEAS_FILTERS["filter"], IV_FILTER]},  # noqa: E501
}  # fmt: skip
IDS = ["EQ:AAA", "EQ:BBB", "EQ:CCC"]


def view(volume: list[float | None] | None, user: str = "bare") -> ReadContext:
    """The screens store; ``volume``: dollar volume of AAA, BBB, CCC on ``day`` (None: no table);
    the personal IV of all three is always stored and always unknown."""
    backend: MemoryBackend = screens_store()
    w = StoreWriter(backend)
    if volume is not None:
        rows = [{"instrument_id": i, "dollar_volume": v} for i, v in zip(IDS, volume, strict=True)]
        write_rows(w, "rollups/instrument/volume@v1", D1, rows)
        iv = [{"instrument_id": i, "iv30_ibkr": None} for i in IDS]
        write_rows(w, "rollups/instrument/ibkr_iv@v1", D1, iv)
    return context(StoreReader(backend), copy.deepcopy(DOCS), user=user)


def by_id(ctx: ReadContext) -> tuple[set[str], dict[str, UnavailableKind]]:
    served = load_served_filters(ctx, "ideas", ctx.session.date)
    return {f.id for f in served.filters}, {w.id: w.unavailable.kind for w in served.withheld}


def test_a_filter_with_no_known_value_for_the_session_is_withheld_as_not_stored() -> None:
    ctx = view([None, None, None])
    offered, withheld = by_id(ctx)
    assert "dollar_volume" not in offered
    assert withheld["dollar_volume"] is UnavailableKind.NOT_STORED
    served = load_served_filters(ctx, "ideas", ctx.session.date)
    [one] = [w for w in served.withheld if w.id == "dollar_volume"]
    assert one.guide == NO_DATA_TERM
    assert one.unavailable.features == ("rollup.volume@v1.dollar_volume",)
    assert one.unavailable.cause.links[0].message == f"no known value for session {D1}"


def test_a_partly_unknown_filter_is_offered() -> None:
    offered, withheld = by_id(view([None, 5e6, None]))
    assert "dollar_volume" in offered and "dollar_volume" not in withheld


def test_a_session_with_no_table_at_all_withholds_it() -> None:
    offered, withheld = by_id(view(None))
    assert "dollar_volume" not in offered
    assert withheld["dollar_volume"] is UnavailableKind.NOT_STORED


def test_an_empty_population_withholds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(no_data, "load_feature_values", lambda *args: {})
    offered, withheld = by_id(view(None))
    assert "dollar_volume" in offered and "dollar_volume" not in withheld


def test_a_licence_withholding_stays_licence_not_no_data() -> None:
    ctx = view([None, None, None])
    _, withheld = by_id(ctx)
    assert withheld["iv"] is UnavailableKind.LICENCE
    [one] = [w for w in load_served_filters(ctx, "ideas").withheld if w.id == "iv"]
    assert one.guide is None


def test_an_input_naming_a_withheld_filter_is_never_refused_and_matches_nothing() -> None:
    ctx = view([None, None, None], "full")
    plain = load_ideas(ctx, 10, None, [])
    shared = load_ideas(ctx, 10, None, [FilterInput("dollar_volume", min=1)])  # a shared link
    assert plain.total > 0 and shared.total == 0  # UNKNOWN never passes
    assert shared.facets is not None and shared.facets.total == plain.total
    off = load_ideas(ctx, 10, None, [FilterInput("dollar_volume", min=1, active=False)])
    assert off.total == plain.total  # echoed switched off: in no mask
