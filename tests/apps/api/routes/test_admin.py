from fastapi.testclient import TestClient


def _cells(body: dict[str, object]) -> dict[tuple[str, str], dict[str, object]]:
    cells = body["cells"]
    assert isinstance(cells, list)
    return {(c["dataset"], c["session"]): c for c in cells}


def test_completeness_grid(client: TestClient) -> None:
    body = client.get("/admin/ingestion/completeness", params={"sessions": 3}).json()
    assert body["sessions"] == ["2022-11-21", "2022-11-22", "2022-11-23"]
    cells = _cells(body)
    assert len(cells) == 3 * len(body["datasets"])
    bars = cells[("bars/1d", "2022-11-23")]
    assert (bars["status"], bars["present"], bars["expected"]) == ("COMPLETE", 11, 11)
    chains = cells[("chains/option_quotes", "2022-11-23")]
    assert (chains["status"], chains["present"], chains["expected"]) == ("PARTIAL", 1, 4)
    assert cells[("chains/option_quotes", "2022-11-22")]["status"] == "MISSING"
    stats = cells[("rollups/instrument/price_stats@v2", "2022-11-23")]
    assert (stats["status"], stats["expected"]) == ("COMPLETE", 4)
    assert cells[("rollups/instrument/price_stats@v2", "2022-11-21")]["status"] == "MISSING"
    reference = cells[("instruments/reference", "2022-11-22")]
    assert (reference["status"], reference["basis"]) == ("CARRIED", "snapshot of 2020-01-01")
    assert cells[("universe", "2022-11-22")]["status"] == "MISSING"
    assert cells[("universe", "2022-11-23")]["status"] == "COMPLETE"


def test_drill_down_chains_groups_underlyings_by_reason(client: TestClient) -> None:
    body = client.get("/admin/ingestion/chains/option_quotes/2022-11-23").json()
    assert body["job"] == "option_chains"
    assert body["cell"]["status"] == "PARTIAL"
    assert body["groups"] == []  # the one stored status is OK
    assert [r["job"] for r in body["runs"]][-1] == "option_chains"


def test_drill_down_groups_run_items(client: TestClient) -> None:
    body = client.get("/admin/ingestion/bars/1d/2022-11-23").json()
    assert body["cell"]["run_ids"]
    assert body["job"] == "daily_bars"


def test_drill_down_not_found(client: TestClient) -> None:
    assert client.get("/admin/ingestion/nope/2022-11-23").status_code == 404
    assert client.get("/admin/ingestion/bars/1d/not-a-date").status_code == 422
