"""``PUT`` / ``DELETE /admin/events/scope/{symbol}``: the admin's change to the event-study scope
list (EV8): the optional reason of an addition and what the write did."""

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class ScopeNameBody(BaseModel):
    note: str = Field("", description="why the name is added (optional, at most 200 characters)")


class ScopeChange(Schema):
    symbol: str = Field(description="the ticker as stored (upper case)")
    listed: bool = Field(description="the symbol is on the effective scope list now")
    changed: bool = Field(
        description="the change was recorded; false: the list already was as asked (a repeat)"
    )
