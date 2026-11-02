"""A named option sleeve (ADR 0088 decision 14): a short put on SPY entered every other session of
January 2024 with a two-point strike-delta grid, each trial's return on collateral measured against
the delta-equivalent stock at the same entry session, by hand."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.edges.document import Edge, parse_edge
from algotrade.config.edges.positions.key import position_key, with_legs
from algotrade.config.edges.positions.templates import KIND, NAME, load_templates
from algotrade.core.time.calendar import sessions_between
from algotrade.data import StoreReader
from algotrade.services.evaluation.cross_section.harness import evaluate_edge
from algotrade.services.evaluation.cross_section.sessions import leg_blocks
from algotrade.services.evaluation.time_series.sleeve import evaluate_sleeve, sleeve_outcomes
from algotrade.services.read.context import UserContext
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore, MemoryConfigStore
from algotrade.storage.tables.result_writer import ResultWriter
from algotrade.storage.tables.schemas import FORWARD_RETURNS, STRUCTURE_PNL
from algotrade.storage.tables.writers import StoreWriter
from tests.conftest import REPO_ROOT
from tests.helpers.stored_frames import (
    reference_rows,
    stamped,
    structure_pnl_row,
    universe_rows,
)
from tests.unit.config.edges.test_document import document
from tests.unit.config.edges.test_named import SLEEVE
from tests.unit.services.evaluation.time_series.conftest import AS_OF, KNOWN, SPY_ID, row

SITE = FileConfigStore(REPO_ROOT / "config", local=False)
TEMPLATES = load_templates(SITE)
FIRST, LAST = date(2024, 1, 2), date(2024, 1, 31)
H = 2
STOCK = 0.01  # SPY's raw return over every hold
# the mid P&L per unit and the entry delta of each trial (the edge's own and the grid's points)
PNL = {"main": (1.0, 0.25), "g_d20": (0.6, 0.20), "g_d30": (1.4, 0.30)}
SPREAD, COLLATERAL = 0.1, 95.0  # half-spreads 0.05 at entry and exit; the strike, cash-secured


def sleeve_edge(**changes: Any) -> Edge:
    return with_legs(parse_edge(document(**{**SLEEVE, **changes}), "drift", "x.toml"), TEMPLATES)


def entries(edge: Edge) -> list[tuple[date, date]]:
    """(D, S) of every leg the schedule places in January."""
    blocks = leg_blocks(edge, None, sessions_between(FIRST, LAST), H)
    return [(leg.decision, leg.entry) for b in blocks for leg in b]


def world(
    edge: Edge,
    skip: frozenset[tuple[str, date]] = frozenset(),
    changes: dict[tuple[str, date], dict[str, Any]] | None = None,
    no_stock: frozenset[date] = frozenset(),
) -> StoreReader:
    """SPY in the reference, its stock return and one trade per trial at each S; ``skip``: the
    (trial, S) with no trade row; ``changes``: fields of a trade row; ``no_stock``: S with no
    stock row."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    snapshot = FIRST - timedelta(days=5)
    universe = universe_rows(["SPY"])
    writer.write_table("universe", snapshot, "u1", stamped(universe, snapshot, "u1"))
    writer.write_table(
        "instruments/reference", snapshot, "u1", stamped(reference_rows(universe), snapshot, "u1")
    )
    keys = {v: position_key(o, H) for v, o in sleeve_outcomes(edge, TEMPLATES)}
    for _, day in entries(edge):
        if day not in no_stock:
            stock = [row(day, STOCK, horizon_sessions=H, window_end=day + timedelta(days=3))]
            frame = stamped(stock, day, f"o-{day}", KNOWN, "outcomes")
            writer.write_table(FORWARD_RETURNS, day, f"o-{day}", frame)
        trades = [
            structure_pnl_row(
                SPY_ID, keys[v], day, hold=H, ts=datetime.combine(day, datetime.min.time(), UTC),
                window_end=day + timedelta(days=3), price_source="option_history",
                licence="personal", entry_spot=100.0, collateral=COLLATERAL,
                **{"pnl_mid": pnl, "position_delta": delta, **(changes or {}).get((v, day), {})},
            )
            for v, (pnl, delta) in PNL.items()
            if v in keys and (v, day) not in skip
        ]  # fmt: skip
        known = (changes or {}).get(("known", day), {}).get("at", KNOWN)
        writer.write_table(STRUCTURE_PNL, day, f"c-{day}", stamped(trades, day, f"c-{day}", known))
    return StoreReader(backend)


def run(reader: StoreReader, edge: Edge, **kwargs: Any) -> Any:
    return evaluate_sleeve(
        reader, edge, sleeve_outcomes(edge, TEMPLATES), FIRST, LAST, AS_OF,
        lambda d: "calm", None, False, **kwargs,
    )  # fmt: skip


def test_a_named_spy_sleeve_with_a_two_point_grid_evaluates_by_hand() -> None:
    edge = sleeve_edge()
    n = len(entries(edge))
    out = run(world(edge), edge)
    assert (out.window, out.horizon, out.scheduled, out.unclosed) == ("every_session", H, n, 0)
    assert [(r.edge_variant, r.symbol) for r in out.results] == [
        ("main", "SPY"), ("g_d20", "SPY"), ("g_d30", "SPY"),
    ]  # fmt: skip
    for r in out.results:
        pnl, delta = PNL[r.edge_variant]
        value = (pnl - SPREAD) / COLLATERAL  # the trade's return on its collateral
        base = delta * 100.0 * STOCK / COLLATERAL  # delta shares bought at the entry spot
        m = r.measures[0]
        assert (m.picks, m.eligible, m.excluded_missing) == (n, n, 0)
        assert m.mean_excess_picks == pytest.approx(value)
        assert m.bh_mean == pytest.approx(base)
        assert m.decile_spread == pytest.approx(value - base)
        assert [v for _, v in r.paired] == pytest.approx([value - base] * n)
        assert (m.hit_rate, m.base_rate) == (1.0, 1.0) and r.lost == {} and r.randoms == ()
        assert len(r.trades) == n and set(r.trades["capital_basis"]) == {"cash_secured"}
        assert r.trades["return_on_capital"].tolist() == pytest.approx([value] * n)
    assert len({r.identity for r in out.results}) == 3  # each trial its own position key


def test_a_missing_or_unmeasured_trade_is_lost_with_its_reason_and_no_stock_leaves_it_unpaired(
) -> None:  # fmt: skip
    edge = sleeve_edge()
    (_, s0), (_, s1), (_, s2), *_ = entries(edge)
    reader = world(
        edge, skip=frozenset({("main", s0)}),
        changes={("main", s1): {"outcome_status": "UNMEASURED", "outcome_reason": "NO_CHAIN",
                                "pnl_mid": None, "option_pnl": None, "stock_pnl": None}},
        no_stock=frozenset({s2}),
    )  # fmt: skip
    main = run(reader, edge).results[0]
    assert main.lost == {"NO_OUTCOME": 1, "UNMEASURED:NO_CHAIN": 1}
    m = main.measures[0]
    n = len(entries(edge))
    assert (m.picks, m.eligible, m.excluded_missing) == (n - 2, n - 3, 1)


def test_a_trade_not_known_at_as_of_is_not_read() -> None:
    edge = sleeve_edge()
    (_, s0), *_ = entries(edge)
    late = {("known", s0): {"at": AS_OF + timedelta(days=1)}}
    out = run(world(edge, changes=late), edge)
    assert {r.lost.get("NO_OUTCOME") for r in out.results} == {1}


def test_a_gated_sleeve_keeps_its_open_sessions_and_slices_the_rest() -> None:
    edge = sleeve_edge()
    n = len(entries(edge))
    out = run(world(edge), edge, gate=lambda d: "open" if d.day < 16 else "closed")
    main = out.results[0]
    opened = sum(d.day < 16 for d, _ in entries(edge))
    assert len(main.in_window) == opened and main.measures[0].picks == opened
    gates = {m.slice_value: m.picks for m in main.measures if m.slice_kind == "gate"}
    assert gates == {"open": opened, "closed": n - opened}


def test_evaluate_edge_gives_one_trial_per_grid_point_and_variant_of_the_sleeve() -> None:
    edge = sleeve_edge(variants=[{"id": "wide", "outcome": {"strike_delta": 0.15}}])
    reader = world(edge)
    configs = MemoryConfigStore({("site", KIND, NAME): SITE.load("site", KIND, NAME)})
    ev = evaluate_edge(
        reader, ResultWriter(MemoryBackend()), configs, UserContext("site"), edge, FIRST, LAST,
        AS_OF,
    )  # fmt: skip
    found = [(r.edge_variant, r.variant) for r in ev.results]
    assert found == [("main", "SPY"), ("wide", "SPY"), ("g_d20", "SPY"), ("g_d30", "SPY")]
    assert ev.trials == 4 and len({r.config_hash for r in ev.results}) == 4
    wide = ev.results[1]
    assert wide.lost_sessions == {"NO_OUTCOME": len(entries(edge))}  # no trade stored for it
    main = ev.results[0].measures[0]
    assert main.mean_excess_picks == pytest.approx(
        (1.0 - SPREAD - 0.013) / COLLATERAL
    )  # the site's commission: 0.65 a contract at entry and exit, per unit
    assert main.trials == 4  # every grid point and variant counts in the deflated Sharpe ratio


def test_a_variant_that_moves_the_entry_reads_its_own_sessions_and_keys() -> None:
    edge = sleeve_edge(
        variants=[{"id": "late", "outcome": {"start_offset_sessions": 2}}], variant_grid=None
    )
    late = dict(sleeve_outcomes(edge, TEMPLATES))["late"]
    shifted = replace(edge, outcome=late, variants=())
    assert entries(shifted) != entries(edge)
    reader = world(edge)  # trades only at main's entries, under main's key
    main, moved = run(reader, edge).results
    assert moved.edge_variant == "late" and main.lost == {}
    # its own sessions, its own key: never main's rows read as its trades
    assert moved.lost == {"NO_OUTCOME": len(entries(shifted))} and moved.in_window == ()
