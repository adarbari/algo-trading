"""``tab_of`` and ``load_session_setups``: the tab of a setup's position (any option leg is
Premium), and qualifying versus left out, point in time (ADR 0083 decision 2)."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from algotrade.config.edges.positions.templates import parse_templates
from algotrade.services.read.ideas import setups

CTX: Any = SimpleNamespace(
    session=SimpleNamespace(date=date(2026, 11, 2)), user=SimpleNamespace(user_id="me")
)
TEMPLATES = parse_templates(
    {
        "template": [
            {
                "id": "long_shares",
                "legs": [{"kind": "shares", "qty": 100}],
                "collateral": "notional",
            },
            {
                "id": "short_put",
                "legs": [
                    {"kind": "option", "right": "P", "qty": -1, "strike": "delta", "delta": 0.3}
                ],
                "collateral": "cash_secured",
            },
        ]
    }
)


@pytest.fixture(autouse=True)
def _templates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setups, "load_templates", lambda configs: TEMPLATES)
    CTX.configs = None


@pytest.mark.parametrize(
    ("position", "structure", "tab"),
    [
        ("long_shares", None, "stocks"),
        ("short_put", None, "premium"),
        (None, "put_wing", "premium"),
    ],
)
def test_the_tab_is_the_kind_of_the_position(
    monkeypatch: pytest.MonkeyPatch, position: str | None, structure: str | None, tab: str
) -> None:
    named = SimpleNamespace(template=position) if position else None
    outcome = SimpleNamespace(position=named, kind="x", structure=structure)
    monkeypatch.setattr(setups, "position_of", lambda o: (position,) if position else None)
    assert setups.tab_of(CTX, outcome) == tab


def _doc(edge_id: str, screeners: tuple[str, ...] = ("scr",)) -> Any:
    outcome = SimpleNamespace(position=None, kind="excess_return", structure=None, side="long")
    return SimpleNamespace(id=edge_id, owner="site", outcome=outcome, screeners=screeners, top_k=5)


def test_setups_qualify_or_are_left_out_by_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    docs = [_doc(i) for i in ("works_e", "weak_e", "newer_e", "stale_e", "old_e", "untested")]
    edges = {d.id: SimpleNamespace(id=d.id, name=d.id, mine=False) for d in docs}
    summaries = {
        "works_e": SimpleNamespace(
            verdict="works", lift_pts=1.0, oos_trades=9, basis_screener="scr", basis_horizon=5
        ),
        "weak_e": SimpleNamespace(
            verdict="not_working", lift_pts=0.0, oos_trades=9, basis_screener="scr", basis_horizon=5
        ),
        "old_e": SimpleNamespace(
            verdict="works", lift_pts=1.0, oos_trades=9, basis_screener=None, basis_horizon=None
        ),
    }
    monkeypatch.setattr(setups, "parsed_edges", lambda ctx, user: tuple(docs))
    monkeypatch.setattr(setups, "load_edges", lambda ctx: tuple(edges.values()))

    def canonical(ctx: Any, edge: Any, bounded: bool = False) -> Any:
        has = not (bounded and edge.id == "newer_e") and edge.id != "untested"
        return SimpleNamespace(run=object() if has else None)

    monkeypatch.setattr(setups.runs, "load_canonical_run", canonical)
    monkeypatch.setattr(
        setups, "load_stored_summary", lambda ctx, e, bounded=False: summaries.get(e.id)
    )
    found = setups.load_session_setups(CTX)
    assert [s.edge.id for s in found.qualifying] == ["works_e"]
    assert found.left_out == {
        ("stocks", setups.NEWER_RUN): ("newer_e",),
        ("stocks", setups.NO_VERDICT): ("stale_e",),
        ("stocks", setups.NO_BASIS): ("old_e",),
    }  # an untested setup (no run at all) is neither listed nor counted
    assert setups.in_tab(CTX, "stocks")("scr") and not setups.in_tab(CTX, "premium")("scr")
    assert setups.in_tab(CTX, "stocks")("own_screen")  # one no setup lists: Stocks
    assert not setups.in_tab(CTX, "premium")("own_screen")
