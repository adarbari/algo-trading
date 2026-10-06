"""Who may read a field (ADR 0040): ``AdminOnly``, the one enforcement point of the graph.

A field that serves ops data (the Admin area: nightly runs and run records, data quality,
ingestion completeness, review lists) carries ``extensions=[AdminOnly()]``; before its resolver
runs the caller (``info.context.viewer``, the registry user the authenticator resolved) must
have ``Role.ADMIN``, else the field fails with a ``FORBIDDEN`` error (``errors.py``; as for any
field error, the response's ``data`` is null where the field is non-null). The web's workspace
guard only hides these pages; this is the enforcement.
``tests/apps/api/graphql/test_permissions.py`` lists every field of the ops types and fails for
one that lacks it."""

from collections.abc import Awaitable, Callable
from typing import Any

from strawberry.extensions.field_extension import FieldExtension
from strawberry.types import Info

from algotrade.config.site.users import Role
from algotrade.core.model.errors import PermissionDeniedError

MESSAGE = "this field is for admins only"


class AdminOnly(FieldExtension):
    """Refuses a field to a caller who is not an admin, before the resolver runs."""

    @staticmethod
    def _check(info: Info) -> None:
        if info.context.viewer.role is not Role.ADMIN:
            raise PermissionDeniedError(MESSAGE)

    def resolve(self, next_: Callable[..., Any], source: Any, info: Info, **kwargs: Any) -> Any:
        self._check(info)
        return next_(source, info, **kwargs)

    async def resolve_async(
        self, next_: Callable[..., Awaitable[Any]], source: Any, info: Info, **kwargs: Any
    ) -> Any:
        self._check(info)
        return await next_(source, info, **kwargs)
