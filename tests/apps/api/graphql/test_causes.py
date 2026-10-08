"""Role-scoped causes (ADR 0056): the cause behind a gap is withheld by the server, never filtered
by the browser. Structure (found in the schema, so a new field is checked without a line here):
every field returning a ``Cause`` carries ``AdminCause``, and no string field that words a cause
(detail / error / message / problems / unresolved / missing*) is readable by a trader unless it
is role-scoped, an Admin type or listed in ``architecture/cause_fields.toml``. Behaviour over the
golden store: a trader's response over every root that can carry an UNKNOWN holds no table path
and a null cause; an admin gets the chain, source to features."""

import json
import re
import tomllib
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from graphql import GraphQLError
from strawberry.types import ExecutionResult

from algotrade.config.site.users import Role
from algotrade.core.model.errors import MissingDataError
from algotrade.services.read.availability.cause import (
    GENERIC_REASONS,
    TABLE_PREFIXES,
    UnavailableKind,
)
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.graphql.errors import NO_DATA, response_of
from algotrade_api.graphql.permissions import AdminCause, AdminOnly
from algotrade_api.graphql.schema import schema
from algotrade_api.main import create_app
from tests.apps.api.graphql.conftest import Graph
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import END, PREVIOUS, as_user

CAUSE_WORDS = re.compile(
    r"^(detail|error|message|problems|unresolved|reason|why|note|notes|table|tables|missing.*)$"
)
OPS = "algotrade_api.graphql.types.ops."
TRADER_OPS = (OPS + "backtest", OPS + "config")
CHAIN = "cause { links { level subject status message runId } }"
UNKNOWN = f"code reason kind guideTerm {CHAIN}"
GAPS = f"unavailable {{ kind features guideTerm {CHAIN} }}"
GAPS_QUERY = f"""query($date: Date, $names: [FeatureName!]!, $dist: FeatureName!) {{
  session(date: $date) {{ {GAPS} }}
  instrument(key: "CCC", date: $date) {{
    features(names: $names) {{ name unknown {{ {UNKNOWN} }} }}
  }}
  regime(date: $date) {{ unknownReason {{ {UNKNOWN} }} }}
  distribution(name: $dist, date: $date) {{ unknown {{ {UNKNOWN} }} }}
  table(columns: $names, date: $date) {{ session {{ {GAPS} }} {GAPS} }}
  ideas(limit: 3, date: $date) {{
    screeners {{
      notRun {{ {UNKNOWN} }}
      run {{ audit {GAPS} }}
    }}
  }}
}}"""
NAMES = ["rollup.earnings@v1.next_earnings_date", "rollup.price_stats@v2.hv20"]
VARIABLES = {"names": NAMES, "dist": NAMES[0]}


def _unwrap(kind: Any) -> Any:
    while hasattr(kind, "of_type"):
        kind = kind.of_type
    return kind


def _definitions() -> list[Any]:
    """Every object type of the schema (``StrawberryObjectDefinition``)."""
    found = []
    for named in schema._schema.type_map.values():
        definition = getattr(named, "extensions", {}).get("strawberry-definition")
        if definition is not None and hasattr(definition, "fields"):
            found.append(definition)
    return found


def _listed() -> set[str]:
    document = tomllib.loads((REPO_ROOT / "architecture" / "cause_fields.toml").read_text())
    return {
        e["name"]
        for kind in ("fact", "legacy")
        for e in document.get(kind, [])
        if e.get("surface", "graphql") == "graphql"
    }


def _free_form(kind: Any) -> bool:
    """A string or a JSON document: a place free text (or a table) can hide."""
    inner = _unwrap(kind)
    return inner is str or "JSON" in str(inner)


def _is_admin_type(definition: Any) -> bool:
    module = str(definition.origin.__module__)
    return module.startswith(OPS) and module not in TRADER_OPS


def _admin(field: Any) -> bool:
    return any(isinstance(e, (AdminCause, AdminOnly)) for e in field.extensions)


def test_every_cause_field_carries_admin_cause() -> None:
    """A field that returns a ``Cause`` is null for a trader (the type itself is only ever
    reached through one)."""
    bare = [
        f"{d.name}.{f.python_name}"
        for d in _definitions()
        for f in d.fields
        if getattr(_unwrap(f.type), "__name__", "") == "Cause" and not _admin(f)
    ]
    assert bare == []


def test_no_cause_wording_is_readable_by_a_trader_unless_listed() -> None:
    listed = _listed()
    loose = [
        f"{d.name}.{f.python_name}"
        for d in _definitions()
        if d.name not in ("Cause", "CauseLink") and not _is_admin_type(d)
        for f in d.fields
        if (CAUSE_WORDS.match(f.python_name) or "JSON" in str(_unwrap(f.type)))
        and _free_form(f.type)
        and not _admin(f)
        and f"{d.name}.{f.python_name}" not in listed
    ]
    assert loose == [], "role-scope it (AdminCause) or justify it in architecture/cause_fields.toml"


def test_every_listed_field_exists() -> None:
    known = {f"{d.name}.{f.python_name}" for d in _definitions() for f in d.fields}
    assert sorted(_listed() - known) == [], "a listed field that is gone: delete its line"


@pytest.fixture(scope="module")
def as_role(api_golden: tuple[ReadStore, dict[str, str]]) -> Callable[[Role], Graph]:
    def graph_for(role: Role) -> Graph:
        user = "ana" if role is Role.ADMIN else "bob"
        app = create_app(
            ApiSettings("memory://", "config"), api_golden[0], authenticator=as_user(user, role)
        )
        client = TestClient(app)

        def post(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
            response = client.post("/graphql", json={"query": query, "variables": variables})
            assert response.status_code == 200, response.text
            body: dict[str, Any] = response.json()
            return body

        return post

    return graph_for


def _causes(node: Any) -> list[Any]:
    """Every ``cause`` value in ``node`` (any depth)."""
    if isinstance(node, dict):
        return [v for k, v in node.items() if k == "cause"] + [
            c for v in node.values() for c in _causes(v)
        ]
    if isinstance(node, list):
        return [c for v in node for c in _causes(v)]
    return []


def test_a_trader_reads_no_table_and_no_cause_over_every_unknown_root(
    as_role: Callable[[Role], Graph],
) -> None:
    trader = as_role(Role.TRADER)
    for day in (PREVIOUS, END):
        body = trader(GAPS_QUERY, {**VARIABLES, "date": day.isoformat()})
        assert "errors" not in body, body
        text = json.dumps(body)
        assert [p for p in TABLE_PREFIXES if p in text] == []
        assert "IB Gateway" not in text
        causes = _causes(body["data"])
        assert causes and all(c is None for c in causes)
    values = trader(GAPS_QUERY, {**VARIABLES, "date": PREVIOUS.isoformat()})["data"]
    gap = next(v["unknown"] for v in values["instrument"]["features"] if v["unknown"])
    assert gap["guideTerm"]
    assert values["session"]["unavailable"], "a trader still learns which features are out"


def test_an_admin_reads_the_chain_from_the_source_to_the_features(
    as_role: Callable[[Role], Graph],
) -> None:
    body = as_role(Role.ADMIN)(GAPS_QUERY, {**VARIABLES, "date": END.isoformat()})
    assert "errors" not in body, body
    gaps = body["data"]["session"]["unavailable"]
    chain = next(g["cause"]["links"] for g in gaps if "ibkr_iv@v1" in json.dumps(g["cause"]))
    levels = ["SOURCE", "STEP", "TABLE", "TABLE", "FEATURE"]  # the gateway-fed input, its rollup
    assert [link["level"] for link in chain] == levels
    assert chain[0]["message"] == "IB Gateway unreachable"
    assert (chain[1]["subject"], chain[1]["status"]) == ("ibkr-iv", "SKIPPED")
    assert chain[1]["runId"] and chain[2]["subject"] == "volatility/ibkr_iv30"
    assert chain[3]["subject"] == "rollups/instrument/ibkr_iv@v1"
    unknown = next(v["unknown"] for v in body["data"]["instrument"]["features"] if v["unknown"])
    assert unknown["cause"]["links"] and "rollups/" in json.dumps(unknown["cause"])


def test_an_error_about_missing_data_is_generic_for_a_trader() -> None:
    error = GraphQLError(
        "rollups/instrument/x@v1 is unreadable",
        original_error=MissingDataError("rollups/instrument/x@v1", "unreadable", "rerun it"),
    )
    result = ExecutionResult(data=None, errors=[error])
    shown = response_of(result)["errors"][0]  # type: ignore[typeddict-item]
    assert shown["extensions"]["code"] == NO_DATA
    assert shown["message"] == GENERIC_REASONS[UnavailableKind.SYSTEM]
    admin = response_of(result, admin=True)["errors"][0]  # type: ignore[typeddict-item]
    assert "rollups/instrument/x@v1" in admin["message"]


IBKR_IV = "rollup.ibkr_iv@v1.iv30_ibkr"
KIND_QUERY = """query($date: Date, $names: [FeatureName!]!) {
  instrument(key: "AAA", date: $date) { features(names: $names) { name unknown { code kind } } }
}"""


def test_a_gap_behind_a_skipped_step_is_system_not_not_stored(
    as_role: Callable[[Role], Graph],
) -> None:
    """The gateway was down (ibkr-iv SKIPPED) and the rollup SUCCEEDED empty: the row is absent
    (NO_ROW) but a failure stands behind it, so a trader is told SYSTEM (owner rule, ADR 0056)."""
    body = as_role(Role.TRADER)(KIND_QUERY, {"date": END.isoformat(), "names": [IBKR_IV, NAMES[1]]})
    gaps = {v["name"]: v["unknown"] for v in body["data"]["instrument"]["features"]}
    assert gaps[IBKR_IV]["kind"] == "SYSTEM", gaps


def test_an_internal_error_is_generic_for_a_trader() -> None:
    error = GraphQLError("IB Gateway refused: rollups/x", original_error=RuntimeError("boom"))
    result = ExecutionResult(data=None, errors=[error])
    shown = response_of(result)["errors"][0]  # type: ignore[typeddict-item]
    assert shown["message"] == GENERIC_REASONS[UnavailableKind.SYSTEM]
    admin = response_of(result, admin=True)["errors"][0]  # type: ignore[typeddict-item]
    assert "IB Gateway" in admin["message"]
