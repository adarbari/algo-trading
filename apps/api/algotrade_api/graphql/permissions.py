"""Who may read a field (ADR 0040): ``AdminOnly``, the one enforcement point of the graph, and
``AdminCause`` (ADR 0056), its sibling for the cause behind a gap.

A field that serves ops data (the Admin area: nightly runs and run records, data quality,
ingestion completeness, review lists) carries ``extensions=[AdminOnly()]``; before its resolver
runs the caller (``info.context.viewer``, the registry user the authenticator resolved) must
have ``Role.ADMIN``, else the field fails with a ``FORBIDDEN`` error (``errors.py``; as for any
field error, the response's ``data`` is null where the field is non-null). The web's workspace
guard only hides these pages; this is the enforcement.

``AdminCause`` is for a field that explains why a fact is not available (``Unknown.cause``,
``Unavailable.cause``, the legacy table lists): it never fails. For a caller who is not an admin
it resolves to its fallback (null, or an empty list) without running the resolver, so a trader's
query that selects it still succeeds and never pays for the chain. The role decides, not the
workspace: an admin on a trader page is served the cause. The browser never filters it.
``tests/apps/api/graphql/test_permissions.py`` lists every field of the ops types and fails for
one that lacks it."""

from collections.abc import Awaitable, Callable
from typing import Any

from strawberry.extensions.field_extension import FieldExtension
from strawberry.types import Info

from algotrade.config.site.users import Role
from algotrade.core.model.errors import PermissionDeniedError

MESSAGE = "this field is for admins only"


def is_admin(info: Info) -> bool:
    """Whether the caller of this request is an admin (the registry's role, ADR 0040)."""
    return bool(info.context.viewer.role is Role.ADMIN)


class AdminCause(FieldExtension):
    """Serves a cause field to an admin only; anyone else gets ``fallback`` (null or ``[]``)
    and the resolver does not run."""

    def __init__(
        self, fallback: Any = None, public: Callable[[Any, Any], Any] | None = None
    ) -> None:
        """``public(source, value)``: when the field has a public form (a generic sentence, an
        audit without its table keys), the resolver runs and this makes the value the caller
        reads; without it the caller gets ``fallback`` and the resolver does not run."""
        self.fallback = fallback
        self.public = public

    def resolve(self, next_: Callable[..., Any], source: Any, info: Info, **kwargs: Any) -> Any:
        if is_admin(info):
            return next_(source, info, **kwargs)
        if self.public is None:
            return self.fallback
        return self.public(source, next_(source, info, **kwargs))

    async def resolve_async(
        self, next_: Callable[..., Awaitable[Any]], source: Any, info: Info, **kwargs: Any
    ) -> Any:
        if is_admin(info):
            return await next_(source, info, **kwargs)
        if self.public is None:
            return self.fallback
        return self.public(source, await next_(source, info, **kwargs))


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
