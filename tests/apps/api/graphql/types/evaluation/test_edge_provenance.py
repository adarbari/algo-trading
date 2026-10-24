"""``Edge.provenance``: the line under the verdict, as the request's caller. Everyone reads the
state, the figures and the sentence with the short run id; the full run id is the admin's
(ADR 0056) and is never filtered in the browser; an edge with no run has none."""

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
from tests.unit.services.read.evaluation.conftest import END, FROZEN, write_run

QUERY = """query Provenance {
  edges(ids: ["drift"]) {
    provenance {
      state evaluatedSession sessionsBehind screenerChanged shortId variantsTried
      reEvaluating line runId
    }
  }
}"""


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


def provenance(backend: MemoryBackend, role: Role) -> dict[str, Any] | None:
    ctx = context(backend, END)

    def opener(user: UserContext, requested: date | None) -> ReadContext:
        return ctx

    request = RequestContext(opener, UserRecord("me", role))
    result = asyncio.run(schema.execute(QUERY, context_value=request))
    assert result.errors is None, result.errors
    assert result.data is not None
    (edge,) = result.data["edges"]
    found: dict[str, Any] | None = edge["provenance"]
    return found


def test_everyone_reads_the_line_and_only_an_admin_the_full_run_id(backend: MemoryBackend) -> None:
    write_run(backend, "run-1", FROZEN, 0.6, trials_counted=3)
    trader = provenance(backend, Role.TRADER)
    assert trader is not None
    assert (trader["state"], trader["sessionsBehind"], trader["variantsTried"]) == ("CURRENT", 0, 3)
    assert trader["line"].startswith("Evaluated on the 30 Sep session, today's data. Run ")
    assert trader["runId"] is None  # never filtered in the browser
    admin = provenance(backend, Role.ADMIN)
    assert admin is not None and admin["runId"] == "run-1" and admin["line"] == trader["line"]


def test_an_edge_with_no_run_has_no_provenance(backend: MemoryBackend) -> None:
    assert provenance(backend, Role.TRADER) is None
