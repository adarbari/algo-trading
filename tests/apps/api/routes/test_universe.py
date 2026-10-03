from fastapi.testclient import TestClient


def _symbols(body: dict[str, object]) -> list[str]:
    page = body["page"]
    assert isinstance(page, dict)
    return [row["symbol"] for row in page["items"]]


def test_universe_defaults_to_the_latest_snapshot(client: TestClient) -> None:
    body = client.get("/universe").json()
    assert body["session"] == body["snapshot_date"] == "2022-11-23"
    assert _symbols(body) == ["AAA", "BBB", "BULL", "CCC"]
    first = body["page"]["items"][0]
    assert (first["sector"], first["liquidity_class"], first["is_leveraged"]) == (
        "Technology",
        "A",
        False,
    )


def test_universe_filters(client: TestClient) -> None:
    assert _symbols(client.get("/universe?leveraged=true").json()) == ["BULL"]
    assert _symbols(client.get("/universe?liquidity_class=a").json()) == ["AAA", "BULL"]
    assert _symbols(client.get("/universe?sector=technology").json()) == ["AAA"]
    assert _symbols(client.get("/universe?q=bb").json()) == ["BBB"]
    assert _symbols(client.get("/universe?security_type=ETF").json()) == []


def test_universe_pages(client: TestClient) -> None:
    body = client.get("/universe", params={"page": 2, "size": 3}).json()
    assert (body["page"]["total"], body["page"]["page"], body["page"]["size"]) == (4, 2, 3)
    assert _symbols(body) == ["CCC"]
    assert client.get("/universe", params={"size": 5000}).status_code == 422


def test_universe_before_any_snapshot_uses_the_earliest(client: TestClient) -> None:
    body = client.get("/universe", params={"date": "2021-01-04"}).json()
    assert body["pre_snapshot"] is True


def test_review_lists(client: TestClient) -> None:
    figi = client.get("/admin/review/figi").json()
    assert figi["source"].startswith("universe_build-")
    assert [r["symbol"] for r in figi["items"]] == ["BBB"]
    leveraged = client.get("/admin/review/leveraged").json()
    assert [r["symbol"] for r in leveraged["items"]] == ["CCC"]
