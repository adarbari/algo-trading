"""A named-symbol setup's stored row (ADR 0088 decision 9, 2.12): one row under ``@named`` per
session, a decision day by the calendar window, the named symbols the snapshot knows, the setup
gate applied as for a screener setup, and a symbol nobody knows said, never dropped silently."""

from datetime import date
from types import SimpleNamespace

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.evaluation.edge_picks.named import decides, is_named, named_night
from algotrade.services.evaluation.edge_picks.night import (
    GATE_CLOSED,
    NOT_DECISION_DAY,
    PICKED,
    SKIPPED,
    Night,
)
from algotrade.services.evaluation.time_series.periods import periods
from algotrade.services.screening.regime import MARKET
from algotrade.storage.tables.edge_schemas import NAMED
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import edge
from tests.unit.services.evaluation.time_series.conftest import (
    FIRST,
    LAST,
    SPY_ID,
    WINDOW,
    World,
    build_world,
    timed_edge,
)

D = next(p.decision for p in periods(WINDOW, FIRST, LAST) if p.inside)
SYMBOLS = {"where": {"all": [{"field": "instrument.symbol", "op": "in", "value": ["SPY", "ZZZ"]}]}}


def _night(w: World, day: date = D) -> Night:
    return Night(w.reader, w.configs, UserContext("site"), day)


def test_a_named_setup_picks_its_symbols_under_named_on_its_decision_day() -> None:
    w = build_world()
    row = named_night(_night(w), timed_edge())
    assert (row.screener, row.status, row.pick_ids, row.pick_sides) == (
        NAMED, PICKED, (SPY_ID,), ("long",)
    )  # fmt: skip
    assert is_named(timed_edge()) and not is_named(edge())
    assert is_named(SimpleNamespace(base="delta_equivalent"))  # type: ignore[arg-type]  # X1


def test_a_session_that_is_no_windows_decision_is_not_a_decision_day() -> None:
    row = named_night(_night(build_world(), D.replace(day=D.day - 7)), timed_edge())
    assert (row.status, row.pick_ids) == (NOT_DECISION_DAY, ())


def test_a_symbol_no_snapshot_knows_is_said_and_none_known_is_skipped() -> None:
    w = build_world()
    row = named_night(_night(w), timed_edge(universe=SYMBOLS))
    assert row.status == PICKED and row.pick_ids == (SPY_ID,) and "ZZZ" in row.reason
    only = {"where": {"all": [{"field": "instrument.symbol", "op": "in", "value": ["ZZZ"]}]}}
    gone = named_night(_night(w), timed_edge(universe=only))
    assert (gone.status, gone.pick_ids) == (SKIPPED, ()) and "ZZZ" in gone.reason


def test_a_closed_setup_gate_stores_gate_closed_for_a_named_setup() -> None:
    w = build_world()
    label = {"instrument_id": MARKET, "label": "STRESS", "market_stress": 80.0}
    w.writer.write_table("rollups/market/regime@v3", D, "m1", stamped([label], D, "m1"))
    gate = {"all": [{"field": "market.regime@v3.label", "op": "not_in", "value": ["STRESS"]}]}
    row = named_night(_night(w), timed_edge(gate=gate))
    assert row.status == GATE_CLOSED and row.pick_ids == () and row.reason


def test_a_plain_scheduled_sleeve_decides_every_session_and_a_timed_edge_needs_its_window() -> None:
    """index_put_ladder (and X3's every_session sleeve) store a row every session: the picks are
    what the setup takes that night; a time-series edge with no window or trigger is refused."""

    def plain(schedule: str, base: str) -> SimpleNamespace:
        return SimpleNamespace(id="x", market_trigger=None, schedule=schedule, base=base)

    w = build_world()
    for schedule in ("every_session_ladder", "every_session"):
        assert decides(w.reader, plain(schedule, "delta_equivalent"), D)  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match="not a time-series edge"):
        decides(w.reader, plain("every_session", "out_of_window"), D)  # type: ignore[arg-type]
