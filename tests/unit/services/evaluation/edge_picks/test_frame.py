"""The ``results/edge_picks`` framer (ADR 0081, ADR 0088 decision 9): sides and a book's weights
are aligned with the picks, and a row that is not a book stores no weights (null, never zeros)."""

from datetime import UTC, date, datetime

from algotrade.services.evaluation.edge_picks.frame import edge_picks_frame
from algotrade.services.evaluation.edge_picks.night import GATE_CLOSED, PICKED, EdgePicks
from algotrade.storage.tables.edge_schemas import EDGE_PICKS

D = date(2026, 11, 2)
NOW = datetime(2026, 11, 2, 23, tzinfo=UTC)


def test_sides_and_weights_are_stored_beside_the_picks_and_no_book_stores_no_weights() -> None:
    rows = [
        EdgePicks("pair", "s", PICKED, ("EQ:A", "EQ:B"), pick_sides=("long", "short")),
        EdgePicks("book", "s", PICKED, ("EQ:A", "EQ:B"), pick_sides=("long", "long"),
                  pick_weights=(0.6, 0.4)),
        EdgePicks("gated", "s", GATE_CLOSED, reason="regime=STRESS"),
    ]  # fmt: skip
    frame = edge_picks_frame(rows, D, "run-1", NOW).set_index("edge_id")
    assert list(frame.loc["pair", "pick_sides"]) == ["long", "short"]
    assert frame.loc["pair", "pick_weights"] is None
    assert list(frame.loc["book", "pick_weights"]) == [0.6, 0.4]
    assert frame.loc["gated", "status"] == GATE_CLOSED
    assert list(frame.loc["gated", "pick_sides"]) == []
    assert {"pick_sides", "pick_weights"} <= {c.name for c in EDGE_PICKS.columns}
