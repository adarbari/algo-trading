"""``Query.edgeResult``: the sections of an edge's result over a stored run, as the request's
caller. A trader reads the public kind of a gap and never the table a lost input lost; an admin
reads it (ADR 0056); a missing edge is null, a section reads only when selected."""

import asyncio
from datetime import date
from typing import Any

import pytest

from algotrade.config.site.users import Role, UserRecord
from algotrade.config.user import UserContext
from algotrade.services.read.context import ReadContext
from algotrade.storage.backends.memory import MemoryBackend
from algotrade_api.graphql.context import RequestContext
from algotrade_api.graphql.schema import schema
from tests.unit.services.read.edge_desk.conftest import context
from tests.unit.services.read.edge_evidence.stored_result import DAYS, stored_run
from tests.unit.services.read.evaluation.conftest import FROZEN, series_row


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


QUERY = """query Result($id: String!) {
  edgeResult(id: $id) {
    id
    basis { runId variant horizonSessions oosHidden unknown { kind } }
    curve {
      kind unit
      points { exit cumulative period }
      gaps { from to kind unknown { kind cause { links { subject } } } }
      live { state points { sell } }
    }
    drawdown { unit episodes { depth } maxInSample }
    rollingStarts { starts { start trades } }
    monthly { months { month value } }
    decay { measure bars { period state } }
  }
}"""
LOST = {"picks": None, "pick_mean": None}


def run(backend: MemoryBackend, role: Role, edge_id: str = "drift") -> dict[str, Any]:
    ctx = context(backend, date(2026, 10, 5))

    def opener(user: UserContext, requested: date | None) -> ReadContext:
        return ctx

    request = RequestContext(opener, UserRecord("me", role))
    result = asyncio.run(schema.execute(QUERY, {"id": edge_id}, context_value=request))
    assert result.errors is None, result.errors
    assert result.data is not None
    return result.data


def stored(backend: MemoryBackend) -> None:
    stored_run(
        backend,
        [
            series_row(DAYS[0], FROZEN),
            series_row(
                DAYS[1], FROZEN, status="lost_input", lost_table="rollups/price_stats@v2", **LOST
            ),
            series_row(DAYS[2], FROZEN),
        ],
    )


def test_the_sections_are_about_the_verdicts_run_and_basis(backend: MemoryBackend) -> None:
    stored(backend)
    found = run(backend, Role.TRADER)["edgeResult"]
    assert found["id"] == "drift"
    assert (found["basis"]["variant"], found["basis"]["horizonSessions"]) == ("momo", 20)
    assert found["basis"]["runId"] == "r1" and found["basis"]["unknown"] is None
    curve = found["curve"]
    assert (curve["kind"], curve["unit"], len(curve["points"])) == (
        "cumulative_excess",
        "excess_return",
        2,
    )
    assert curve["live"] == {"state": "none", "points": []}
    assert [e["depth"] for e in found["drawdown"]["episodes"]] == []
    assert found["monthly"]["months"] and found["decay"]["bars"][-1] == {
        "period": "live",
        "state": "not_stored",
    }


def test_a_trader_reads_the_kind_of_a_lost_input_and_an_admin_the_table(
    backend: MemoryBackend,
) -> None:
    stored(backend)
    (gap,) = run(backend, Role.TRADER)["edgeResult"]["curve"]["gaps"]
    assert gap["kind"] == "lost_input" and gap["unknown"]["kind"] == "SYSTEM"
    assert gap["unknown"]["cause"] is None  # never the table, never filtered in the browser
    (seen,) = run(backend, Role.ADMIN)["edgeResult"]["curve"]["gaps"]
    assert [link["subject"] for link in seen["unknown"]["cause"]["links"]] == [
        "rollups/price_stats@v2"
    ]


def test_an_edge_with_no_run_is_not_run_in_every_section_and_a_missing_edge_is_null(
    backend: MemoryBackend,
) -> None:
    found = run(backend, Role.TRADER)["edgeResult"]
    assert found["basis"]["variant"] is None and found["basis"]["unknown"] == {"kind": "NOT_RUN"}
    assert found["curve"]["points"] == [] and found["rollingStarts"]["starts"] == []
    assert run(backend, Role.TRADER, "no-such-edge")["edgeResult"] is None
