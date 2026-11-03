"""``POST /users`` (ID5): an admin onboards a trader; a trader is refused; the registry the
app (and its Supabase authenticator) reads is the reloaded one."""

import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from algotrade.config.site.users import UsersSettings
from algotrade_api.auth.keys import KeySet
from algotrade_api.auth.supabase import SupabaseAuthenticator
from tests.apps.api.conftest import SUPABASE_URL, Tokens

BODY = {"user_id": "zoe", "email": "Zoe@Example.com", "name": "Zoe"}


def test_an_admin_onboards_a_trader_and_gets_the_provider_step(
    writer_client: TestClient, root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="algotrade_api.routes.authoring.users"):
        sent = writer_client.post("/users", json=BODY)
    assert (sent.status_code, sent.json()) == (
        200,
        {
            "user_id": "zoe",
            "role": "trader",
            "pending_provider": True,
            "provider_step": {"email": "zoe@example.com", "instruction": "supabase_add_user"},
        },
    )
    written = tomllib.loads((root / "users" / "zoe" / "identity.toml").read_text())
    assert (written["email"], written["name"], written["declared_by"]) == (
        "zoe@example.com", "Zoe", "local",
    )  # fmt: skip
    assert "declared_at" in written
    assert "alice" in (root / "site" / "users.toml").read_text()
    assert "zoe" not in (root / "site" / "users.toml").read_text()  # never edited
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("onboard")]
    assert lines == ["onboard user=zoe role=trader by=local"]
    assert "example.com" not in caplog.text


def test_a_trader_is_refused_and_nothing_is_written(trader_client: TestClient, root: Path) -> None:
    sent = trader_client.post("/users", json=BODY)
    assert sent.status_code == 403
    assert not (root / "users" / "zoe").exists()


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({**BODY, "user_id": "alice"}, 409),  # in users.toml
        ({**BODY, "user_id": "site"}, 400),
        ({**BODY, "user_id": "Not Valid"}, 400),
        ({**BODY, "email": "nope"}, 400),
        ({"user_id": "zoe"}, 422),
    ],
)
def test_refusals_map_to_the_http_statuses(
    writer_client: TestClient, root: Path, body: dict[str, Any], status: int
) -> None:
    assert writer_client.post("/users", json=body).status_code == status
    assert not (root / "users" / "zoe").exists()


def test_a_second_onboarding_of_the_same_id_or_email_is_a_conflict(
    writer_client: TestClient,
) -> None:
    assert writer_client.post("/users", json=BODY).status_code == 200
    assert writer_client.post("/users", json={**BODY, "email": "x@example.com"}).status_code == 409
    taken = writer_client.post("/users", json={**BODY, "user_id": "zed"})
    assert taken.status_code == 409 and "example.com" not in taken.text


def test_the_app_registry_and_the_supabase_authenticator_follow_the_write(
    writer_client: TestClient, tokens: Tokens, root: Path
) -> None:
    app = writer_client.app
    keys = KeySet(tokens.fetch())
    keys.refresh()
    # the app's authenticator in supabase mode reads ``app.state.users`` as it is now
    auth = SupabaseAuthenticator(SUPABASE_URL, lambda: app.state.users, keys, tokens.secret)  # type: ignore[attr-defined]
    token = tokens.mint("HS256", kid=None, email="zoe@example.com")
    users: UsersSettings = app.state.users  # type: ignore[attr-defined]
    assert users.by_email("zoe@example.com") is None
    assert writer_client.post("/users", json=BODY).status_code == 200
    assert app.state.users.by_email("zoe@example.com").user_id == "zoe"  # type: ignore[attr-defined]
    request = _bearer(token)
    assert auth.authenticate(request).user_id == "zoe"
    assert auth.authenticate(request).role.value == "trader"


def _bearer(token: str) -> Any:
    headers = [(b"authorization", f"Bearer {token}".encode())]
    return Request({"type": "http", "headers": headers, "server": ("10.0.0.1", 443)})


def test_concurrent_onboardings_all_authenticate_afterwards(writer_client: TestClient) -> None:
    names = ["za", "zb", "zc", "zd"]
    with ThreadPoolExecutor(4) as pool:
        codes = list(
            pool.map(
                lambda n: (
                    writer_client.post(
                        "/users", json={"user_id": n, "email": f"{n}@example.com"}
                    ).status_code
                ),
                names,
            )
        )
    assert codes == [200] * 4
    users = writer_client.app.state.users  # type: ignore[attr-defined]
    assert all(users.by_email(f"{n}@example.com") is not None for n in names)
