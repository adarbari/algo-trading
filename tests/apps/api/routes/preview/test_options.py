"""``POST /preview/options/{roll,calls}``: what a trader types stays out of request logs and
caches (body only, no query parameter, ``Cache-Control: no-store``, no log record carries a
typed figure), a gap is served in public words with its cause for an admin only, an undefined
figure is null (never NaN), and an unknown ticker is a 404."""

import logging
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from algotrade.config.site.users import Role
from algotrade.services.preview.options import calls, roll
from algotrade.services.read.availability.cause import Cause, table_cause
from algotrade.services.read.values import Unknown, UnknownCode
from algotrade_api.deps import ApiSettings, ReadStore
from algotrade_api.main import create_app
from algotrade_api.routes.preview import options as route
from tests.helpers.api_store import as_user

PATHS = ("/preview/options/roll", "/preview/options/calls")
EXPIRY = date(2022, 12, 23)
ROLL = {"key": "AAA", "strike": 87.125, "expiry": EXPIRY.isoformat(), "sold_at": 1.4375}
CALLS = {"key": "AAA", "shares": 4321, "price": 83.6125}
TYPED = ("87.125", "1.4375", "4321", "83.6125")


def test_the_calculators_take_a_body_only_and_no_query_parameter(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()["paths"]
    for path in PATHS:
        post = spec[path]["post"]
        assert "requestBody" in post and not post.get("parameters")
        assert set(spec[path]) == {"post"}  # no GET: nothing typed goes in a URL


def test_nothing_typed_reaches_a_log_and_no_answer_is_cached(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        answers = [client.post(PATHS[0], json=ROLL), client.post(PATHS[1], json=CALLS)]
    for answer in answers:
        assert answer.status_code == 200, answer.text
        assert answer.headers["cache-control"] == "no-store"
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert not any(figure in logged for figure in TYPED)


def test_a_gap_is_public_words_and_its_cause_is_an_admins_only(
    api_golden: tuple[ReadStore, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def as_role(role: Role) -> TestClient:
        settings = ApiSettings("memory://", "config")
        return TestClient(create_app(settings, api_golden[0], authenticator=as_user(role=role)))

    cause = table_cause("rates/treasury", "no curve on or before 2022-11-23")
    found = Unknown(UnknownCode.NO_PARTITION, cause)
    monkeypatch.setattr(route.roll, "preview_roll", lambda *a, **k: found)
    trader = as_role(Role.TRADER).post(PATHS[0], json=ROLL).json()
    assert trader["preview"] is None and trader["gap"]["cause"] is None
    assert trader["gap"]["code"] == "NO_PARTITION" and "rates" not in trader["gap"]["kind_text"]
    admin = as_role(Role.ADMIN).post(PATHS[0], json=ROLL).json()
    assert admin["gap"]["cause"][0]["subject"] == "rates/treasury"


def test_an_unknown_ticker_is_not_found(client: TestClient) -> None:
    assert client.post(PATHS[0], json={**ROLL, "key": "NOPE"}).status_code == 404
    assert client.post(PATHS[1], json={**CALLS, "key": "NOPE"}).status_code == 404


def test_bad_figures_are_rejected(client: TestClient) -> None:
    assert client.post(PATHS[0], json={**ROLL, "strike": 0}).status_code == 422
    assert client.post(PATHS[1], json={**CALLS, "shares": -1}).status_code == 422


def _unknown() -> Unknown:
    return Unknown(UnknownCode.NULL, Cause(()))


def test_a_roll_is_served_flat_with_an_undefined_figure_null(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = roll.Contract("put", 85.0, EXPIRY)
    later = EXPIRY + timedelta(days=7)
    preview = roll.RollPreview(
        "EQ:AAA", date(2022, 11, 23), 84.2, contract, 1.4, 1.85, 0.45, -0.0094, 30,
        float("nan"),
        (roll.Roll(later, 85.0, 0.48, 83.12, 0.0686, -0.54, None, _unknown()),),
    )  # fmt: skip
    monkeypatch.setattr(route.roll, "preview_roll", lambda *a, **k: preview)
    got = client.post(PATHS[0], json=ROLL).json()["preview"]
    assert (got["right"], got["strike"], got["buy_back"], got["delta"]) == ("put", 85.0, 1.85, None)
    row = got["rolls"][0]
    assert (row["extra_credit"], row["new_breakeven"], row["report_inside"]) == (0.48, 83.12, None)
    assert row["report_inside_unknown"]["kind"] == "NOT_STORED"


def test_calls_carry_their_totals_and_an_unknown_dividend(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = calls.CallRow(EXPIRY, 30, 85.0, 2.13, 0.0255, 0.042, False, True, None, None, None)
    preview = calls.CallsPreview(
        "EQ:AAA", date(2022, 11, 23), 84.2, 1, 0.007, (row,), (213.0,), _unknown()
    )
    monkeypatch.setattr(route.calls, "preview_calls", lambda *a, **k: preview)
    got = client.post(PATHS[1], json=CALLS).json()["preview"]
    assert got["rows"][0]["premium_total"] == 213.0 and got["contracts"] == 1
    assert got["dividend"] is None and got["dividend_unknown"]["code"] == "NULL"
