"""The Ideas page's first load stays within its transfer budget (owner decision 2026-10-22,
docs/decisions/log.md "Ideas page size": 50 ideas, 300 KB): the web app's own ``IdeasPage``
document and fact names over a store of 400 picks each with stored values (the Ideas rule's caps
lifted so 400 are ideas), asked for the first page; the next page's cursor then continues it (the
browser's whole sequence)."""

import gzip
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from algotrade.config.user import UserContext
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user, store_over
from tests.unit.services.read.screens.conftest import CONFIGS, screens_store, write_big_run

WEB = Path(__file__).parents[6] / "apps/web/src/entities/idea"
BUDGET_BYTES = 300 * 1024
PICKS = 400


def _document() -> str:
    text = (WEB / "api/hooks.ts").read_text()
    found = re.search(r"graphql\(`(.*?)`\)", text, re.S)
    assert found, "the IdeasPage document is no longer a graphql() literal in entities/idea"
    return found.group(1)


def _names() -> list[str]:
    return re.findall(r"feature\('([^']+)'\)", (WEB / "model/facts.ts").read_text())


def _client() -> TestClient:
    backend = screens_store()
    write_big_run(backend, PICKS, frozen=True, criteria=8)
    wide = {("site", "ranking", "ideas"): {"site_top": 500, "user_top": 500}}
    store = store_over(backend, MemoryConfigStore({**CONFIGS, **wide}), UserContext("me"))
    return TestClient(
        create_app(ApiSettings("memory://", "config"), store, authenticator=as_user("me"))
    )


def _post(client: TestClient, after: str | None, first: int = 50) -> tuple[dict, int, int]:  # type: ignore[type-arg]
    body = {"query": _document(), "variables": {"first": first, "after": after, "names": _names()}}
    response = client.post("/graphql", json=body, headers={"Accept-Encoding": "identity"})
    assert response.status_code == 200, response.text
    raw = response.content
    parsed = json.loads(raw)
    assert "errors" not in parsed, parsed
    return parsed["data"]["ideas"], len(raw), len(gzip.compress(raw))


def test_the_first_load_of_fifty_ideas_is_within_the_transfer_budget() -> None:
    client = _client()
    page, raw, zipped = _post(client, None)
    assert len(page["items"]) == 50 and page["total"] >= PICKS and page["hasMore"]
    assert zipped <= BUDGET_BYTES, f"first load {zipped} bytes gzip, {raw} raw"
    _, bigger_raw, _ = _post(client, None, first=100)
    assert raw < bigger_raw  # the page size is what the payload follows


def test_the_next_page_continues_the_first_over_the_wire() -> None:
    client = _client()
    first, _, _ = _post(client, None)
    second, _, zipped = _post(client, first["nextCursor"])
    assert [i["rank"] for i in second["items"]] == list(range(51, 101))
    assert not {i["instrumentId"] for i in first["items"]} & {
        i["instrumentId"] for i in second["items"]
    }
    assert zipped <= BUDGET_BYTES
