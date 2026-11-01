"""The arguments and context every read resolver of the root ``Query`` shares: ``Day`` (the session
to read) and ``Ctx`` (the request's ``RequestContext``)."""

import datetime as dt
from typing import Annotated

import strawberry
from strawberry.types import Info

from algotrade_api.graphql.context import RequestContext

Day = Annotated[
    dt.date | None,
    strawberry.argument(
        description="the session to read (default: the latest with bars); every value "
        "below is for exactly this date"
    ),
]
Ctx = Info[RequestContext, None]
