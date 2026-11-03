"""The setup gate in the paper record (ADR 0088 decision 7, G15; E9): read at the signal
session as tonight's picks read it. Open, the record buys what an ungated edge would; closed, it
buys nothing and says the gate's reason; unknown, the signal is skipped (fail closed). A
``portfolio.*`` rule reads the record's own book as the cut-off knew it, so a gated record opens,
fills, closes and reopens from its own trades; an ungated edge never reads a gate."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from algotrade.config.edges.loading import load_edges
from algotrade.services.evaluation.forward import signals as signals_module
from algotrade.services.evaluation.forward.results import run_night
from algotrade.services.evaluation.forward.signals import EdgeSignals, edge_signals
from algotrade.services.screening.regime import MARKET
from algotrade.storage.tables.edge_schemas import EDGE_PAPER
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import DAYS, World, build_world
from tests.unit.services.evaluation.forward.conftest import NOW, USER, Desk, desk

REGIME = "rollups/market/regime@v3"
NOT_STRESS = {"all": [{"field": "market.regime@v3.label", "op": "not_in", "value": ["STRESS"]}]}
FLAT = {"all": [{"field": "portfolio.open_positions", "op": "lt", "value": 1}]}
SIGNAL, KNOWN = date(2026, 8, 27), datetime(2026, 8, 28, 22, tzinfo=UTC)


def labelled(label: str) -> World:
    """The world with the market regime ``label`` stored at the first session."""
    w = build_world()
    row = {"instrument_id": MARKET, "label": label, "market_stress": 80.0}
    w.writer.write_table(REGIME, DAYS[0], "m1", stamped([row], DAYS[0], "m1"))
    return w


def signals(d: Desk, day: date = DAYS[0], as_of: datetime | None = None) -> EdgeSignals:
    (edge,) = load_edges(d.configs, "u1")
    return edge_signals(d.world.reader, d.configs, USER, edge, DAYS[0], day, as_of)


def held(w: World, *names: str, known: datetime = KNOWN) -> None:
    """``u1``'s paper trades of ``drift`` signalled before the first session, open through it."""
    rows = [
        {
            "user_id": "u1", "edge_id": "drift", "signal_session": SIGNAL, "instrument_id": n,
            "status": "open", "buy_session": date(2026, 8, 28), "sell_session": DAYS[3],
            "rank": 1, "horizon_sessions": 2, "delisted": False, "licence": "open",
        }
        for n in names
    ]  # fmt: skip
    w.writer.write_table(EDGE_PAPER.name, SIGNAL, "p1", stamped(rows, SIGNAL, "p1", known, "x"))


def test_an_open_gate_buys_exactly_what_the_ungated_edge_buys() -> None:
    w = labelled("CALM")
    gated = signals(desk(w, gate=NOT_STRESS))
    assert gated.closed is None and gated.skipped is None
    assert gated == signals(desk(w))


def test_a_closed_gate_buys_nothing_and_says_the_gates_reason() -> None:
    found = signals(desk(labelled("STRESS"), gate=NOT_STRESS))
    assert found.signals == () and found.skipped is None
    assert found.closed and found.screener == "momo"  # due and decided: not "not due"


def test_an_unknown_gate_skips_the_signal_never_buys() -> None:
    found = signals(desk(build_world(), gate=NOT_STRESS))  # no market row stored
    assert found.signals == () and found.closed is None
    assert "setup gate is unknown" in (found.skipped or "")


def test_a_portfolio_gate_reads_the_records_own_book_at_the_cutoff() -> None:
    w = build_world()
    held(w, "EQ:N01")
    d = desk(w, gate=FLAT)
    assert signals(d, as_of=NOW).closed  # one trade open: open_positions < 1 is false
    assert len(signals(d, as_of=KNOWN - timedelta(days=1)).signals) == 5  # not yet known: flat


def test_another_edges_or_owners_trades_are_not_the_book() -> None:
    w = build_world()
    rows = [
        {
            "user_id": user, "edge_id": edge_id, "signal_session": SIGNAL,
            "instrument_id": "EQ:N01", "status": "open", "buy_session": date(2026, 8, 28),
            "sell_session": DAYS[3], "rank": 1, "horizon_sessions": 2, "delisted": False,
            "licence": "open",
        }
        for user, edge_id in (("u2", "drift"), ("u1", "other"))
    ]  # fmt: skip
    w.writer.write_table(EDGE_PAPER.name, SIGNAL, "p1", stamped(rows, SIGNAL, "p1", KNOWN, "x"))
    assert len(signals(desk(w, gate=FLAT), as_of=NOW).signals) == 5


def test_a_gated_record_opens_closes_and_reopens_from_its_own_trades() -> None:
    """Night 1 starts flat and buys; the next due session holds those trades (closed, with the
    gate's reason); once they are sold the gate opens again."""
    d = desk(gate=FLAT)

    def tonight(day: date, offset: int) -> dict[str, Any]:
        now = NOW + timedelta(days=offset)
        _, record = run_night(d.world.reader, d.world.results, d.configs, USER, day, now)
        return dict(record.stats["tonight"]["drift"])

    assert tonight(DAYS[0], 0) == {"state": "signalled", "reason": ""}
    shut = tonight(DAYS[2], 1)  # bought DAYS[1], sold DAYS[3]: open at DAYS[2]
    assert shut["state"] == "no_picks" and shut["reason"]
    assert tonight(DAYS[4], 2) == {"state": "signalled", "reason": ""}


def test_an_ungated_edge_never_reads_a_gate_or_a_book(monkeypatch: pytest.MonkeyPatch) -> None:
    before = signals(desk())

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("an ungated edge read a gate")

    monkeypatch.setattr(signals_module, "edge_gate", refuse)
    monkeypatch.setattr(signals_module, "paper_row", refuse)
    after = signals(desk())
    assert after == before and len(after.signals) == 5
