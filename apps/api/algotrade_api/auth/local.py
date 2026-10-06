"""``ALGOTRADE_AUTH=off`` (ADR 0040): the development shortcut that serves one fixed registry
user without a token, and only on a loopback address. The CLI refuses to start that way on
another ``--host`` (``require_loopback``), and every request is checked again against the
address the server accepted it on, so a misconfigured bind still answers 401. A request a
proxy forwarded (``Forwarded`` / ``X-Forwarded-For``, or Tailscale Funnel's
``Tailscale-Funnel-Request``: a tunnel or reverse proxy on this machine makes remote callers
look local, ADR 0043) is 401 too."""

import ipaddress

from starlette.requests import Request

from algotrade.config.site.users import UserRecord
from algotrade.core.model.errors import ConfigurationError
from algotrade_api.auth.protocol import UnauthenticatedError

LOCALHOST = "localhost"
# Set by a proxy in front of the app; Tailscale Serve / Funnel set X-Forwarded-For, and Funnel
# also Tailscale-Funnel-Request (ADR 0043).
FORWARDED = ("forwarded", "x-forwarded-for", "tailscale-funnel-request")


def is_loopback(host: str) -> bool:
    """``localhost`` or a loopback IP (``127.0.0.0/8``, ``::1``; brackets allowed)."""
    if host.strip().lower() == LOCALHOST:
        return True
    try:
        return ipaddress.ip_address(host.strip().strip("[]")).is_loopback
    except ValueError:
        return False


def require_loopback(host: str) -> None:
    """Refuse to serve without authentication on a non-loopback address."""
    if not is_loopback(host):
        raise ConfigurationError(
            f"ALGOTRADE_AUTH=off serves without a token: bind to a loopback address, not {host!r}"
        )


class LocalAuthenticator:
    """Every request on a loopback address is ``user``; any other is 401."""

    def __init__(self, user: UserRecord) -> None:
        self._user = user

    def authenticate(self, request: Request) -> UserRecord:
        server = request.scope.get("server")
        if not server or not is_loopback(str(server[0])):
            raise UnauthenticatedError("authentication is off: only loopback requests are served")
        if any(h in request.headers for h in FORWARDED):
            raise UnauthenticatedError("authentication is off: forwarded requests are refused")
        return self._user
