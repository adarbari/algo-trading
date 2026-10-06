"""The authenticator seam (ADR 0040 decision 5): a request in, the registry user out, or
``UnauthenticatedError`` (401: no token, or one that does not verify) or ``ForbiddenError``
(403: a valid token for nobody in the registry). Roles always come from the registry, never
the provider. Messages are generic: they never carry a token, a claim or an email."""

from typing import Protocol

from starlette.requests import Request

from algotrade.config.site.users import UserRecord


class UnauthenticatedError(Exception):
    """No credentials, or credentials that do not verify (HTTP 401)."""


class ForbiddenError(Exception):
    """A verified caller the registry does not let in (HTTP 403)."""


class Authenticator(Protocol):
    def authenticate(self, request: Request) -> UserRecord:
        """The registry user making ``request`` (``UnauthenticatedError``: 401,
        ``ForbiddenError``: 403)."""
        ...
