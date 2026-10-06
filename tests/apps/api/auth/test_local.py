"""``ALGOTRADE_AUTH=off``: one fixed user, on a loopback address only."""

import pytest
from starlette.requests import Request

from algotrade.config.site.users import Role, UserRecord
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.local import LocalAuthenticator, is_loopback, require_loopback
from algotrade_api.auth.protocol import UnauthenticatedError

LOCAL = UserRecord("local", Role.ADMIN, "Local user")


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("127.8.0.1", True),
        ("::1", True),
        ("[::1]", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.1.5", False),
        ("example.com", False),
        ("", False),
    ],
)
def test_is_loopback(host: str, loopback: bool) -> None:
    assert is_loopback(host) is loopback


def test_require_loopback_refuses_a_public_bind() -> None:
    require_loopback("127.0.0.1")
    with pytest.raises(ConfigurationError, match="loopback"):
        require_loopback("0.0.0.0")


def _request(server: tuple[str, int] | None) -> Request:
    return Request({"type": "http", "headers": [], "server": server})


def test_serves_the_fixed_user_on_loopback_only() -> None:
    auth = LocalAuthenticator(LOCAL)
    assert auth.authenticate(_request(("127.0.0.1", 8000))) == LOCAL
    for server in (("10.0.0.2", 8000), ("testserver", 80), None):
        with pytest.raises(UnauthenticatedError):
            auth.authenticate(_request(server))
