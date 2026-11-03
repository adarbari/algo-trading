"""A ``portfolio.*`` setup gate at tonight's picks (ADR 0088 G15): the book is the edge's paper
record as the previous session's cut-off knew it; with no cut-off, or an edge that records no
paper trades, the book is UNKNOWN and the picks are skipped, never decided on an empty book."""

from datetime import UTC, date, datetime
from typing import Any

from algotrade.config.user import UserContext
from algotrade.services.evaluation.edge_picks.night import (
    GATE_CLOSED,
    NO_PAPER_RECORD,
    PICKED,
    SKIPPED,
    Night,
    edge_night,
)
from algotrade.storage.tables.edge_schemas import EDGE_PAPER
from tests.helpers.stored_frames import stamped
from tests.unit.services.evaluation.cross_section.conftest import DAYS, World, edge

USER = UserContext("site")
GATE = {"all": [{"field": "portfolio.open_positions", "op": "lt", "value": 2}]}
SIGNAL, KNOWN, CUTOFF = (
    date(2026, 8, 27),
    datetime(2026, 8, 28, 22, tzinfo=UTC),
    datetime(2026, 8, 31, 22, tzinfo=UTC),
)


def paper(w: World, *names: str, known: datetime = KNOWN) -> None:
    rows = [
        {
            "user_id": "site", "edge_id": "drift", "signal_session": SIGNAL, "instrument_id": n,
            "status": "open", "buy_session": date(2026, 8, 28), "sell_session": DAYS[3],
            "rank": 1, "horizon_sessions": 2, "delisted": False, "licence": "open",
        }
        for n in names
    ]  # fmt: skip
    w.writer.write_table(EDGE_PAPER.name, SIGNAL, "p1", stamped(rows, SIGNAL, "p1", known, "x"))


def night(w: World, cutoff: datetime | None = CUTOFF) -> Night:
    return Night(w.reader, w.configs, USER, DAYS[0], paper_as_of=cutoff)


def run(w: World, cutoff: datetime | None = CUTOFF, **changes: Any) -> Any:
    (stored,) = edge_night(night(w, cutoff), edge(top_k=3, gate=GATE, **changes))
    return stored


def test_the_book_is_the_paper_record_known_at_the_cutoff(world: World) -> None:
    paper(world, "EQ:N01", "EQ:N02")
    assert run(world).status == GATE_CLOSED  # two open trades: open_positions < 2 is false


def test_a_book_below_the_limit_leaves_the_gate_open(world: World) -> None:
    paper(world, "EQ:N01")
    assert run(world).status == PICKED


def test_a_trade_written_after_the_cutoff_is_not_in_the_book(world: World) -> None:
    paper(world, "EQ:N01", "EQ:N02", known=datetime(2026, 9, 1, 22, tzinfo=UTC))
    assert run(world).status == PICKED


def test_no_cutoff_skips_the_picks_with_the_reason(world: World) -> None:
    paper(world, "EQ:N01", "EQ:N02")
    stored = run(world, None)
    assert (stored.status, stored.reason, stored.pick_ids) == (SKIPPED, NO_PAPER_RECORD, ())


def test_an_edge_that_records_no_paper_trades_skips_the_picks(world: World) -> None:
    stored = run(world, status="researching")
    assert (stored.status, stored.reason) == (SKIPPED, NO_PAPER_RECORD)
