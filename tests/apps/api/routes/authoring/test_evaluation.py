"""``PUT /evaluation/split``: a trader saves their own train / test split (read back by GraphQL
``Query.evaluationSplit``); a date outside the stored range is refused; never the site's file."""

from pathlib import Path

from fastapi.testclient import TestClient

URL = "/evaluation/split"
READ = "{ evaluationSplit { splitFrom latestSession } }"


def read(client: TestClient) -> dict[str, str | None]:
    body = client.post("/graphql", json={"query": READ}).json()
    return body["data"]["evaluationSplit"]  # type: ignore[no-any-return]


def test_a_trader_saves_clears_and_reads_back_their_own_split(
    trader_client: TestClient, root: Path
) -> None:
    latest = read(trader_client)["latestSession"]
    assert read(trader_client)["splitFrom"] is None
    saved = trader_client.put(URL, json={"split_from": latest})
    assert (saved.status_code, saved.json()) == (200, {"split_from": latest})
    assert read(trader_client)["splitFrom"] == latest
    assert f"split_from = {latest}" in (root / "users" / "bob" / "evaluation.toml").read_text()
    cleared = trader_client.put(URL, json={"split_from": None})
    assert (cleared.status_code, cleared.json()) == (200, {"split_from": None})
    assert read(trader_client)["splitFrom"] is None
    assert not (root / "site" / "evaluation.toml").exists()


def test_a_date_beyond_the_stored_sessions_is_refused(
    trader_client: TestClient, root: Path
) -> None:
    for bad in ("2999-01-01", "1990-01-01"):
        assert trader_client.put(URL, json={"split_from": bad}).status_code == 400
    assert not (root / "users").exists()


def test_the_site_user_cannot_write(writer_client: TestClient, root: Path) -> None:
    refused = writer_client.put(URL, json={"split_from": None}, headers={"X-Act-For": "site"})
    assert refused.status_code == 400
    assert not (root / "users").exists()
