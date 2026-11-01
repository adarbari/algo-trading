"""``pick_edges.load_pick_edges`` answers an id no stored list holds with the night's own code:
``ideas/of_setup.py`` relies on it (a probe id) to tell not-a-decision-day, nothing picked, and
not stored apart when nobody counted. This pins that behaviour of the public read."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from algotrade.services.read.evaluation import pick_edges

D = date(2026, 11, 2)
RUN: Any = SimpleNamespace(session=D, owner="site", config_id="scr", run_id="r")
CTX: Any = SimpleNamespace(session=SimpleNamespace(date=D), user=SimpleNamespace(user_id="me"))


def _answer(monkeypatch: pytest.MonkeyPatch, status: str | None) -> str:
    edge = SimpleNamespace(id="e1", name="E", screeners=("scr",), owner="site", top_k=None)
    monkeypatch.setattr(pick_edges, "parsed_edges", lambda ctx, user: [edge])
    monkeypatch.setattr(pick_edges, "load_edges", lambda ctx, ids: [edge])
    frame = pd.DataFrame(
        {"user_id": ["site"], "edge_id": ["e1"], "screener": ["scr"], "status": [status],
         "pick_ids": [["EQ:A"]]}
    )  # fmt: skip
    monkeypatch.setattr(
        pick_edges, "partition", lambda ctx, table: frame if status is not None else frame.iloc[0:0]
    )
    out = pick_edges.load_pick_edges(CTX, RUN, [("~probe", "", 1)])
    return out["~probe"][0].code


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("picked", pick_edges.NOT_COUNTED),
        ("not_decision_day", pick_edges.NOT_A_DECISION_DAY),
        ("unjudged", pick_edges.UNJUDGED),
        ("skipped", pick_edges.NOT_STORED),
        (None, pick_edges.NOT_STORED),
    ],
)
def test_an_id_no_list_holds_reads_the_nights_own_code(
    monkeypatch: pytest.MonkeyPatch, status: str | None, code: str
) -> None:
    assert _answer(monkeypatch, status) == code
