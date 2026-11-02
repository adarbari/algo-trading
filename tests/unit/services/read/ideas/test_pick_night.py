"""``pick_edges.load_pick_edges`` answers an id no stored list holds with the night's own code:
``ideas/of_setup.py`` relies on it (a probe id) to tell not-a-decision-day, nothing picked, and
not stored apart when nobody counted. This pins that behaviour of the public read, and how a closed
setup gate and a pick's side read (ADR 0088 decisions 7, 9)."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.services.read.evaluation import pick_edges

D = date(2026, 11, 2)
RUN: Any = SimpleNamespace(session=D, owner="site", config_id="scr", run_id="r")
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=D), user=SimpleNamespace(user_id="me"))


def _read(
    monkeypatch: pytest.MonkeyPatch, status: str | None, asked: tuple[str, ...] = ("~probe",),
    side: str = "long", **row: Any,
) -> dict[str, pick_edges.PickEdge]:  # fmt: skip
    """``load_pick_edges`` over one stored row (``row``: extra columns, e.g. ``pick_sides``)."""
    edge = SimpleNamespace(
        id="e1", name="E", screeners=("scr",), owner="site", top_k=None,
        outcome=SimpleNamespace(side=side, kind="excess_return"),
    )  # fmt: skip
    monkeypatch.setattr(pick_edges, "parsed_edges", lambda ctx, user: [edge])
    monkeypatch.setattr(pick_edges, "load_edges", lambda ctx, ids: [edge])
    frame = pd.DataFrame(
        {"user_id": ["site"], "edge_id": ["e1"], "screener": ["scr"], "status": [status],
         "pick_ids": [row.pop("pick_ids", ["EQ:A"])], **{k: [v] for k, v in row.items()}}
    )  # fmt: skip
    monkeypatch.setattr(
        pick_edges, "partition", lambda ctx, table: frame if status is not None else frame.iloc[0:0]
    )
    out = pick_edges.load_pick_edges(CTX, RUN, [(i, "", n) for n, i in enumerate(asked, 1)])
    return {i: found[0] for i, found in out.items()}


def _answer(monkeypatch: pytest.MonkeyPatch, status: str | None) -> str:
    return _read(monkeypatch, status)["~probe"].code


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("picked", pick_edges.NOT_COUNTED),
        ("not_decision_day", pick_edges.NOT_A_DECISION_DAY),
        ("gate_closed", pick_edges.PAUSED),
        ("unjudged", pick_edges.UNJUDGED),
        ("skipped", pick_edges.NOT_STORED),
        (None, pick_edges.NOT_STORED),
    ],
)
def test_an_id_no_list_holds_reads_the_nights_own_code(
    monkeypatch: pytest.MonkeyPatch, status: str | None, code: str
) -> None:
    assert _answer(monkeypatch, status) == code


def test_a_closed_setup_gate_pauses_every_name_with_the_gates_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = _read(monkeypatch, "gate_closed", ("~probe", "EQ:A"), reason="regime=STRESS")
    assert {(e.code, e.reason, e.counts) for e in found.values()} == {
        (pick_edges.PAUSED, "regime=STRESS", False)
    }


def test_a_short_pick_is_not_counted_until_the_page_can_say_short_and_by_score_is_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = _read(
        monkeypatch, "picked", ("EQ:A", "EQ:B"), side="long_short",
        pick_ids=["EQ:A", "EQ:B"], pick_sides=["long", "short"],
    )  # fmt: skip
    a, b = found["EQ:A"], found["EQ:B"]
    assert (a.code, a.place, a.side, a.by_score) == (pick_edges.COUNTS, 1, "long", True)
    assert (b.code, b.place, b.side) == (pick_edges.NOT_COUNTED, None, "short")


def test_a_row_written_before_sides_reads_every_pick_long(monkeypatch: pytest.MonkeyPatch) -> None:
    found = _read(monkeypatch, "picked", ("EQ:A",))  # no pick_sides column
    assert (found["EQ:A"].code, found["EQ:A"].side) == (pick_edges.COUNTS, "long")
