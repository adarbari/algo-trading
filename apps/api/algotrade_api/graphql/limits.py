"""How much one request may ask for (ADR 0037): the document limits (depth 8, 10 aliases,
5000 tokens; Strawberry's validation extensions, in ``EXTENSIONS``) and the list caps
(``MaxItems``): at most ``MAX_NAMES`` feature names per ``features(names)`` and ``MAX_PAGE``
rows per ``first`` / ``size``, ``MAX_DAYS`` days ahead and ``MAX_MONTHS`` months of filings
for the event reads. A request over a limit fails with ``BAD_REQUEST``."""

from collections.abc import Awaitable, Callable
from typing import Any

from graphql import GraphQLError
from strawberry.extensions import MaxAliasesLimiter, MaxTokensLimiter, QueryDepthLimiter
from strawberry.extensions.base_extension import SchemaExtension
from strawberry.extensions.field_extension import FieldExtension
from strawberry.types import Info

MAX_DEPTH = 8
MAX_ALIASES = 10
MAX_TOKENS = 5000
MAX_NAMES = 60  # features(names)
MAX_PAGE = 1000  # first / size
MAX_DAYS = 366  # eventStudy(days), eventCalendar(days): calendar days ahead
MAX_MONTHS = 120  # eventStudy(months): months of filings

# Factories: Strawberry builds a fresh extension per request.
EXTENSIONS: tuple[Callable[[], SchemaExtension], ...] = (
    lambda: QueryDepthLimiter(max_depth=MAX_DEPTH),
    lambda: MaxAliasesLimiter(max_alias_count=MAX_ALIASES),
    lambda: MaxTokensLimiter(max_token_count=MAX_TOKENS),
)


class MaxItems(FieldExtension):
    """Refuses a call whose list argument ``argument`` has more than ``limit`` items (or whose
    integer argument is above ``limit``), before the resolver runs."""

    def __init__(self, argument: str, limit: int) -> None:
        self.argument = argument
        self.limit = limit

    def _check(self, kwargs: dict[str, Any]) -> None:
        value = kwargs.get(self.argument)
        size = value if isinstance(value, int) else len(value) if value is not None else 0
        if size > self.limit:
            raise GraphQLError(f"{self.argument}: at most {self.limit}, got {size}")

    def resolve(self, next_: Callable[..., Any], source: Any, info: Info, **kwargs: Any) -> Any:
        self._check(kwargs)
        return next_(source, info, **kwargs)

    async def resolve_async(
        self, next_: Callable[..., Awaitable[Any]], source: Any, info: Info, **kwargs: Any
    ) -> Any:
        self._check(kwargs)
        return await next_(source, info, **kwargs)
