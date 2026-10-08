"""Role-scoped causes over REST (ADR 0056): the response models the routes serve. A string (or
list of strings) field that words a cause (detail / error / message / problems / unresolved /
missing*) declares ``ADMIN_CAUSE`` (so ``redact`` withholds it from a trader) or is listed in
``architecture/cause_fields.toml``; behaviour: the preview and the on-request run answer a
trader without a table path and an admin with it."""

import dataclasses
import json
import re
import tomllib
import typing
from collections.abc import Iterator
from datetime import date
from typing import Any

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from algotrade.config.site.users import Role
from algotrade.services.ondemand.screens import RunRequest
from algotrade.services.read.availability.cause import (
    ADMIN_CAUSE,
    GENERIC_REASONS,
    TABLE_PREFIXES,
    UnavailableKind,
)
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from algotrade_api.redact import redact
from algotrade_api.routes import PUBLIC_ROUTERS, ROUTERS
from tests.conftest import REPO_ROOT
from tests.helpers.api_store import as_user

CAUSE_WORDS = re.compile(r"^(detail|error|message|problems|unresolved|missing.*)$")
DRAFT = {
    "id": "my_draft",
    "kind": "screener",
    "impl": "rules",
    "selection": "liquid_optionable",
    "criteria": {
        "price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5},
        "iv": {"field": "rollup.ibkr_iv@v1.iv30_ibkr", "op": "gt", "value": 0.1, "mode": "score"},
    },
    "columns": {"close": "rollup.price_stats@v2.close"},
}


def _models(tp: Any, seen: set[type]) -> Iterator[type]:
    """Every pydantic model and dataclass reachable from the type ``tp`` (lists, optionals,
    annotated and generic arguments unwrapped)."""
    for arg in typing.get_args(tp):
        yield from _models(arg, seen)
    if isinstance(tp, type) and tp not in seen:
        if issubclass(tp, BaseModel):
            seen.add(tp)
            yield tp
            for f in tp.model_fields.values():
                yield from _models(f.annotation, seen)
        elif dataclasses.is_dataclass(tp):
            seen.add(tp)
            yield tp
            for hint in typing.get_type_hints(tp).values():
                yield from _models(hint, seen)


def _served() -> list[type]:
    seen: set[type] = set()
    found: list[type] = []
    for router in (*PUBLIC_ROUTERS, *ROUTERS):
        for route in router.routes:
            if isinstance(route, APIRoute) and route.response_model is not None:
                found += list(_models(route.response_model, seen))
    return found


def _fields(model: type) -> Iterator[tuple[str, Any, bool]]:
    """(name, annotation, marked) of each field of a served model."""
    if issubclass(model, BaseModel):
        for name, f in model.model_fields.items():
            extra = f.json_schema_extra
            yield name, f.annotation, isinstance(extra, dict) and ADMIN_CAUSE in extra
    else:
        hints = typing.get_type_hints(model)
        for f in dataclasses.fields(model):
            yield f.name, hints[f.name], ADMIN_CAUSE in f.metadata


def _texts(annotation: Any) -> bool:
    """Whether ``annotation`` holds text (a str, or a list or optional of it)."""
    if typing.get_origin(annotation) is dict:  # counts keyed by a name, not words
        return False
    return annotation is str or any(_texts(a) for a in typing.get_args(annotation))


def _listed() -> set[str]:
    document = tomllib.loads((REPO_ROOT / "architecture" / "cause_fields.toml").read_text())
    return {e["name"] for kind in ("fact", "legacy") for e in document.get(kind, [])}


def test_the_served_models_include_the_ones_that_carry_causes() -> None:
    names = {m.__name__ for m in _served()}
    assert {"PreviewCoverage", "ExpressionCheck", "LiveOptionChain", "RunRequest"} <= names


def test_no_cause_wording_is_served_to_a_trader_unless_marked_or_listed() -> None:
    listed = _listed()
    loose = [
        f"{m.__name__}.{name}"
        for m in _served()
        for name, annotation, marked in _fields(m)
        if m.__name__ != "CauseLink"  # reached only through the marked ``cause`` field
        and CAUSE_WORDS.match(name)
        and _texts(annotation)
        and not marked
        and f"{m.__name__}.{name}" not in listed
    ]
    assert loose == [], (
        "mark it ADMIN_CAUSE (redact withholds it) or justify it in cause_fields.toml"
    )


def _client(store: ReadStore, role: Role) -> TestClient:
    user = "local" if role is Role.ADMIN else "arvinder"
    app = create_app(ApiSettings("memory://", "config"), store, authenticator=as_user(user, role))
    return TestClient(app)


def test_the_preview_serves_a_trader_no_table_and_an_admin_the_chain(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    body = {"spec": DRAFT, "limit": 2}
    asked = _client(api_golden[0], Role.TRADER).post("/screeners/preview", json=body)
    assert asked.status_code == 200, asked.text
    trader = asked.json()
    admin = _client(api_golden[0], Role.ADMIN).post("/screeners/preview", json=body).json()
    text = json.dumps(trader)
    assert [
        text[max(0, text.find(p) - 80) : text.find(p) + 60] for p in TABLE_PREFIXES if p in text
    ] == []
    assert trader["coverage"]["missing_tables"] == []
    assert all(u["cause"] is None and u["guide_term"] for u in trader["coverage"]["unavailable"])
    assert admin["coverage"]["missing_tables"], "the golden session lacks ibkr_iv@v1"
    assert trader["coverage"]["unavailable"]
    assert all(u["cause"] for u in admin["coverage"]["unavailable"])


def test_a_failed_run_is_generic_for_a_trader() -> None:
    failed = RunRequest("failed", "x", date(2022, 11, 23), "j", None, "boom")
    assert redact(failed, Role.ADMIN).error == "boom"
    assert redact(failed, Role.TRADER).error == GENERIC_REASONS[UnavailableKind.SYSTEM]
    assert redact(dataclasses.replace(failed, error=None), Role.TRADER).error is None
