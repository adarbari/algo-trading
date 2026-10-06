"""Error codes of the graph (ADR 0037): every error in a response carries
``extensions.code``, mapped here from the library exceptions the REST app maps to statuses.

A response is 200 with ``data`` and ``errors[]``. "No such thing" is a null field and
"nothing stored yet" is never an error (UNKNOWN values, empty lists, ``session.missing``);
a code says what went wrong with the request itself."""

from graphql import GraphQLError
from strawberry.http import GraphQLHTTPResponse
from strawberry.types import ExecutionResult

from algotrade.core.model.errors import ConfigurationError, MissingDataError, PermissionDeniedError
from algotrade.services.read.context import NotFoundError
from algotrade.services.read.instruments.catalogue import UnknownFeatureError

NOT_FOUND = "NOT_FOUND"
BAD_REQUEST = "BAD_REQUEST"  # a malformed request, a failed validation or limit, bad arguments
FORBIDDEN = "FORBIDDEN"  # the caller's role may not read this field (ADR 0040: ops are admin-only)
UNKNOWN_FEATURE = "UNKNOWN_FEATURE"  # a feature name that is not in the caller's catalogue
NO_DATA = "NO_DATA"  # a stored table a read needs is unreadable (not merely absent)
INTERNAL = "INTERNAL"  # a bug: anything not mapped above

# Most specific first: UnknownFeatureError is a ConfigurationError.
_CODES: tuple[tuple[type[Exception], str], ...] = (
    (UnknownFeatureError, UNKNOWN_FEATURE),
    (NotFoundError, NOT_FOUND),
    (PermissionDeniedError, FORBIDDEN),
    (MissingDataError, NO_DATA),
    (ConfigurationError, BAD_REQUEST),
)


def code_of(error: GraphQLError) -> str:
    """The code of ``error``: by the exception a resolver raised, ``BAD_REQUEST`` for an
    error of the request itself (parse, validation, a limit, a bad variable)."""
    original = error.original_error
    if original is None or isinstance(original, GraphQLError):
        return BAD_REQUEST
    for kind, code in _CODES:
        if isinstance(original, kind):
            return code
    if isinstance(original, ValueError):  # a scalar refusing a value (FeatureName)
        return BAD_REQUEST
    return INTERNAL


def response_of(result: ExecutionResult) -> GraphQLHTTPResponse:
    """The JSON body for ``result``: ``data``, and ``errors`` each with ``extensions.code``."""
    body: GraphQLHTTPResponse = {"data": result.data}
    if result.errors:
        body["errors"] = [
            {**e.formatted, "extensions": {**(e.extensions or {}), "code": code_of(e)}}
            for e in result.errors
        ]
    if result.extensions:
        body["extensions"] = result.extensions
    return body
