"""``POST /regime/explain`` (ADR 0041, amended): a canned model's answer becomes the explanation
with its allowed citations, the second ask reads the cache, a number the facts do not contain
withholds the text, the seventh ask in a minute is a 429, a body that asks for neither or both a
400, an unknown card a 404, and no model (or one that is down) a 503."""

import json
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from algotrade.services.explaining.limits import RateLimiter
from algotrade.services.read.regime.regime import MarketRegime, RegimeLabel, load_regime
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from tests.helpers.api_store import as_user
from tests.unit.services.explaining.conftest import Canned, Down
from tests.unit.services.read.regime.conftest import regime_ctx

CURVE = "https://example.org/curve"
GOOD = json.dumps({"text": "A storm: stress is 71 out of 100.", "links": [CURVE, "https://x.io"]})
BAD = json.dumps({"text": "A storm: stress is 99 out of 100.", "links": []})
ASK = {"question": "what is happening?"}


@pytest.fixture(autouse=True)
def stored_regime(monkeypatch: pytest.MonkeyPatch) -> Iterator[MarketRegime]:
    """The golden API store has no market groups: serve the regime of the unit-test store."""
    regime = load_regime(regime_ctx())
    monkeypatch.setattr("algotrade.services.explaining.regime.load_regime", lambda ctx: regime)
    yield regime


def app_with(store: ReadStore, model: Any) -> TestClient:
    app = create_app(
        ApiSettings("memory://", "config"), store, text_model=model, authenticator=as_user()
    )
    return TestClient(app)


def test_the_regime_is_explained_with_its_allowed_links(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    model = Canned(GOOD)
    response = app_with(api_golden[0], model).post("/regime/explain", json=ASK)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "text": "A storm: stress is 71 out of 100.",
        "citations": [{"title": "curve page", "url": CURVE}],  # the other link was not allowed
        "checked": True,
        "note": None,
        "cached": False,
    }
    assert len(model.asked) == 1


def test_a_card_is_explained_by_its_key(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    model = Canned(GOOD)
    response = app_with(api_golden[0], model).post("/regime/explain", json={"card": "trend"})
    assert response.status_code == 200 and model.asked[0][1] == "Plain trend?"


def test_the_second_ask_is_a_cache_hit(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    model = Canned(GOOD)
    client = app_with(api_golden[0], model)
    first, second = (
        client.post("/regime/explain", json=ASK),
        client.post("/regime/explain", json=ASK),
    )
    assert (first.json()["cached"], second.json()["cached"]) == (False, True)
    assert first.json()["text"] == second.json()["text"] and len(model.asked) == 1


def test_an_answer_with_an_invented_number_is_withheld(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    body = app_with(api_golden[0], Canned(BAD)).post("/regime/explain", json=ASK).json()
    assert (body["checked"], body["text"], body["citations"]) == (False, "", [])
    assert "99" in body["note"]


def test_the_seventh_call_in_a_minute_is_a_429(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    client = app_with(api_golden[0], Canned(BAD))  # unchecked answers are never cached
    for _ in range(6):
        assert client.post("/regime/explain", json=ASK).status_code == 200
    response = client.post("/regime/explain", json=ASK)
    assert response.status_code == 429 and "too many requests" in response.json()["detail"]
    assert int(response.headers["Retry-After"]) >= 1


def test_the_limit_is_per_user(api_golden: tuple[ReadStore, dict[str, str]]) -> None:
    client = app_with(api_golden[0], Canned(BAD))
    client.app.state.explain_limiter = RateLimiter(1)  # type: ignore[attr-defined]
    assert client.post("/regime/explain", json=ASK).status_code == 200
    assert client.post("/regime/explain", json=ASK).status_code == 429


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({}, 400),
        ({"question": "what is happening?", "card": "curve"}, 400),
        ({"question": "should I sell?"}, 400),
        ({"card": "nope"}, 404),
        ({"question": "x" * 101}, 422),
    ],
)
def test_bad_asks(
    api_golden: tuple[ReadStore, dict[str, str]], body: dict[str, str], status: int
) -> None:
    assert (
        app_with(api_golden[0], Canned(GOOD)).post("/regime/explain", json=body).status_code
        == status
    )


def test_an_unknown_regime_is_a_400(
    api_golden: tuple[ReadStore, dict[str, str]],
    stored_regime: MarketRegime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unknown = replace(stored_regime, label=RegimeLabel.UNKNOWN)
    monkeypatch.setattr("algotrade.services.explaining.regime.load_regime", lambda ctx: unknown)
    response = app_with(api_golden[0], Canned(GOOD)).post("/regime/explain", json=ASK)
    assert response.status_code == 400 and "not computed" in response.json()["detail"]


def test_no_model_is_a_503_with_the_reason(client: TestClient) -> None:
    response = client.post("/regime/explain", json=ASK)
    assert response.status_code == 503
    assert "config/site/llm.toml" in response.json()["detail"]


def test_an_empty_body_is_the_availability_probe_and_never_calls_the_model(
    api_golden: tuple[ReadStore, dict[str, str]], client: TestClient
) -> None:
    model = Canned(GOOD)
    assert app_with(api_golden[0], model).post("/regime/explain", json={}).status_code == 400
    assert not model.asked  # a model is configured: 400, and nothing was asked of it
    assert client.post("/regime/explain", json={}).status_code == 503  # no model configured


def test_a_model_that_cannot_answer_is_a_503(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    response = app_with(api_golden[0], Down()).post("/regime/explain", json=ASK)
    assert response.status_code == 503 and "timed out" in response.json()["detail"]


def test_an_answer_that_is_not_the_envelope_is_a_503_and_not_cached(
    api_golden: tuple[ReadStore, dict[str, str]],
) -> None:
    client = app_with(api_golden[0], Canned("A storm, but not JSON."))
    response = client.post("/regime/explain", json=ASK)
    assert response.status_code == 503 and "not the JSON envelope" in response.json()["detail"]
    assert client.app.state.explain_cache._items == {}  # type: ignore[attr-defined]
