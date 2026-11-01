"""The licence gate of a setup (ADR 0084 decision 1): a setup whose canonical run joined personal
outcome rows is absent for a viewer without the licence and present for one who holds it; the
screen's own personal fields never hide a setup (ADR 0088 decision B)."""

from typing import Any

import pandas as pd
import pytest

from algotrade.services.evaluation.cross_section.detail.licences import outcome_licence
from algotrade.services.evaluation.edge_picks.frame import RESULT, edge_picks_frame
from algotrade.services.evaluation.edge_picks.night import EdgePicks
from algotrade.services.read.evaluation import edges
from algotrade.services.read.evaluation.pick_edges import COUNTS, load_pick_edges
from algotrade.services.read.evaluation.verdict.evidence_licence import evidence_visible
from algotrade.services.read.screens.runs import ScreenerRun
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.result_writer import ResultWriter
from tests.unit.services.read.evaluation.conftest import (
    DOCS,
    END,
    FROZEN,
    T,
    session_ctx,
    stores,
    write_run,
)

USERS = {
    "owner": {"role": "admin", "licences": ["personal"]},
    "trader": {"role": "trader"},
}


def docs() -> dict[tuple[str, str, str], dict[str, Any]]:
    users = {"user": [{"id": k, **v} for k, v in USERS.items()]}
    return {**DOCS, ("site", "settings", "users"): users}


def ids(backend: MemoryBackend, user: str) -> list[str]:
    return [e.id for e in edges.load_edges(stores(backend, user, docs()))]


def test_a_personal_evidence_setup_is_absent_for_a_trader_and_present_for_the_owner() -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, 0.6, evidence_licence="personal")
    assert ids(backend, "trader") == []
    assert ids(backend, "owner") == ["drift"]


def test_an_open_or_unrecorded_evidence_setup_is_listed_for_everyone() -> None:
    for recorded in ("open", None):  # a run from before the column has none
        backend = MemoryBackend()
        write_run(backend, "official", FROZEN, 0.6, evidence_licence=recorded)
        assert ids(backend, "trader") == ["drift"]


def test_only_the_canonical_run_decides_not_an_older_history_run() -> None:
    backend = MemoryBackend()
    write_run(backend, "older", FROZEN, 0.6, evidence_licence="personal")
    write_run(backend, "newer", FROZEN, 0.6, minutes=5, evidence_licence="open")
    assert ids(backend, "trader") == ["drift"]


def test_a_setup_with_no_run_has_no_evidence_to_hide() -> None:
    ctx = stores(MemoryBackend(), "trader", docs())
    (edge,) = edges.load_edges(ctx)
    assert evidence_visible(ctx, edge)


@pytest.mark.parametrize(
    ("column", "expected"),
    [(None, "open"), ([None, None], "open"), (["open", "personal"], "personal")],
)
def test_the_outcome_licence_is_the_strictest_row(column: Any, expected: str) -> None:
    frame = pd.DataFrame({"x": [1, 2]})
    if column is not None:
        frame["licence"] = column
    assert outcome_licence(frame) == expected


def test_a_personal_evidence_setup_adds_no_pick_for_a_trader() -> None:
    backend = MemoryBackend()
    write_run(backend, "official", FROZEN, 0.6, evidence_licence="personal")
    day = END
    row = EdgePicks("drift", "momo", "picked", ("EQ:AAA",), top_k=5)
    frame = edge_picks_frame([row], day, "picks", T)
    ResultWriter(backend).write_result(RESULT, day, "picks", frame)
    run = ScreenerRun(
        "r", "momo", "site", day, "COMPLETE", T, 1, (), 1, 0, None, {},
    )  # fmt: skip

    def codes(user: str) -> list[str]:
        ctx = session_ctx(stores(backend, user, docs()), day)
        found = load_pick_edges(ctx, run, [("EQ:AAA", "QUALIFIED", 1)])
        return [e.code for e in found.get("EQ:AAA", ())]

    assert codes("trader") == []
    assert codes("owner") == [COUNTS]
