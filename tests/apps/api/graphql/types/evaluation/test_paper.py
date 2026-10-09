"""``Query.edgeDesk`` and ``Query.edgePaper`` over the golden API store: a user who follows no edge
gets an empty desk (never an error), an unknown edge has no paper record, and the served types
carry the read model's figures and sentences unchanged."""

from datetime import date

from algotrade.services.read.edge_desk import desk as desk_read
from algotrade.services.read.edge_desk import live as live_read
from algotrade.services.read.edge_desk import paper as paper_read
from algotrade_api.graphql.types.evaluation.paper import EdgeDesk, EdgePaper
from tests.apps.api.graphql.conftest import Graph

DESK = """query Desk($date: Date) {
  edgeDesk(date: $date) {
    session sellSession
    buys { edgeId instrumentId }
    sells { edgeId instrumentId }
    followed { edgeId name state since record { state closed headline } }
  }
}"""
PAPER = """query Paper($id: String!) {
  edgePaper(id: $id) { edgeId record { state } trades { instrumentId } }
}"""


def test_a_user_who_follows_nothing_gets_an_empty_desk(graph: Graph) -> None:
    body = graph(DESK, {})
    assert "errors" not in body, body
    desk = body["data"]["edgeDesk"]
    assert desk["session"] == "2022-11-23" and desk["sellSession"] > desk["session"]
    assert desk["buys"] == desk["sells"] == desk["followed"] == []


def test_an_unknown_edge_has_no_paper_record(graph: Graph) -> None:
    body = graph(PAPER, {"id": "no-such-edge"})
    assert "errors" not in body, body
    assert body["data"]["edgePaper"] is None


RECORD = live_read.LiveRecord(
    state="on_track", closed=20, wins=12, open=2, skipped=1, win_rate=0.6, backtest_rate=0.6,
    basis="out-of-sample win rate", low=0.4, high=0.8,
    bins=(live_read.RangeBin(0.0, 0.5, 0.3), live_read.RangeBin(0.5, 1.0, 0.7)),
    headline="12 of 20 closed trades won.",
)  # fmt: skip
TRADE = paper_read.PaperTrade(
    "drift", "Drift", "EQ:A", None, "momo", 1, date(2026, 10, 5), date(2026, 10, 6),
    date(2026, 11, 3), 20, "won", "", 0.02, False,
)  # fmt: skip


def test_the_served_types_carry_the_read_models_figures_unchanged() -> None:
    forward = live_read.ForwardTest(
        "drift", "Drift", date(2026, 9, 1), 24, 20, RECORD, RECORD, True, "It can replace the edge."
    )
    paper = EdgePaper.of(live_read.EdgePaper("drift2", RECORD, (TRADE,), forward), None)  # type: ignore[arg-type]
    assert (paper.record.state, paper.record.low, paper.record.high) == ("on_track", 0.4, 0.8)
    assert [b.chance for b in paper.record.bins] == [0.3, 0.7]
    assert paper.trades[0].excess_return == 0.02 and paper.trades[0].instrument is None
    assert paper.forward is not None and paper.forward.can_replace
    desk = EdgeDesk.of(
        desk_read.EdgeDesk(
            date(2026, 10, 5), date(2026, 10, 6), (TRADE,), (),
            (desk_read.FollowedEdge("drift", "Drift", "following", date(2026, 9, 1), RECORD),),
        ),
        None,  # type: ignore[arg-type]
    )  # fmt: skip
    assert [t.instrument_id for t in desk.buys] == ["EQ:A"] and desk.followed[0].record.closed == 20
