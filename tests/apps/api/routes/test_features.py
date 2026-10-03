import pytest
from fastapi.testclient import TestClient


def test_catalogue_lists_instrument_and_rollup_fields(client: TestClient) -> None:
    catalogue = {f["name"]: f for f in client.get("/features").json()}
    hv20 = catalogue["rollup.price_stats@v1.hv20"]
    assert (hv20["kind"], hv20["dtype"], hv20["version"], hv20["rollup"]) == (
        "rollup",
        "float",
        1,
        "price_stats@v1",
    )
    assert "bars/1d" in hv20["inputs"]
    assert catalogue["instrument.sector"]["source"] == "instruments/company"


def test_numeric_distribution(client: TestClient) -> None:
    body = client.get("/features/rollup.price_stats@v1.hv20/distribution").json()
    assert (body["session"], body["count"], body["nulls"]) == ("2022-11-23", 4, 1)
    assert body["quantiles"]["0.5"] == pytest.approx(0.21)
    assert sum(b["count"] for b in body["histogram"]) == 3
    earlier = client.get(
        "/features/rollup.price_stats@v1.hv20/distribution", params={"date": "2022-11-22"}
    ).json()
    assert earlier["session"] == "2022-11-22"


def test_categorical_distribution(client: TestClient) -> None:
    body = client.get("/features/instrument.security_type/distribution").json()
    assert {c["value"]: c["count"] for c in body["categories"]} == {"COMMON_STOCK": 3, "ETF": 1}


def test_distribution_not_found(client: TestClient) -> None:
    assert client.get("/features/rollup.nope@v1.x/distribution").status_code == 404
    unstored = "/features/rollup.earnings@v1.earnings_time/distribution"
    assert client.get(unstored).status_code == 404
