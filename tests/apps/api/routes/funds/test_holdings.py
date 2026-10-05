from fastapi.testclient import TestClient


def test_top_ten_holdings_of_an_etf_by_ticker_or_id(client: TestClient) -> None:
    by_ticker = client.get("/instruments/bull/holdings").json()
    assert by_ticker == client.get("/instruments/EQ:BULL/holdings").json()
    assert by_ticker["instrument_id"] == "EQ:BULL" and by_ticker["is_etf"] is True
    assert (by_ticker["as_of"], by_ticker["source"], by_ticker["total"]) == (
        "2022-11-22",
        "test",
        40,
    )
    items = by_ticker["items"]
    assert [i["rank"] for i in items] == list(range(1, 11))  # the default is the top ten
    assert items[0] == {
        "rank": 1,
        "name": "AAA Corp",
        "symbol": "AAA",
        "instrument_id": "EQ:AAA",
        "weight": 0.25,
        "asset_class": "Equity",
    }


def test_holdings_outside_the_universe_keep_their_name_only(client: TestClient) -> None:
    items = client.get("/instruments/BULL/holdings", params={"top": 4}).json()["items"]
    assert len(items) == 4
    caterpillar, cash = items[2], items[3]
    assert (caterpillar["name"], caterpillar["symbol"], caterpillar["instrument_id"]) == (
        "Caterpillar",
        "CAT",
        None,
    )
    assert (cash["name"], cash["symbol"], cash["instrument_id"]) == ("US Dollar", None, None)


def test_the_latest_read_replaces_an_older_one(client: TestClient) -> None:
    body = client.get("/instruments/BULL/holdings", params={"top": 100}).json()
    assert len(body["items"]) == 12  # the older read's OLD line is gone
    assert "Old Holding" not in {i["name"] for i in body["items"]}


def test_an_unknown_instrument_is_a_404(client: TestClient) -> None:
    assert client.get("/instruments/NOPE/holdings").status_code == 404


def test_a_stock_is_a_200_with_nothing(client: TestClient) -> None:
    response = client.get("/instruments/AAA/holdings")
    assert response.status_code == 200
    assert response.json() == {
        "instrument_id": "EQ:AAA",
        "is_etf": False,
        "as_of": None,
        "source": None,
        "total": 0,
        "items": [],
    }


def test_top_is_between_1_and_1000(client: TestClient) -> None:
    assert client.get("/instruments/BULL/holdings", params={"top": 0}).status_code == 422
    assert client.get("/instruments/BULL/holdings", params={"top": 1001}).status_code == 422
