"""``/configs``: config summaries and one resolved config."""

from typing import Any

from pydantic import Field

from algotrade_api.schemas.health import Schema


class ConfigSummary(Schema):
    config_id: str
    scope: str = Field(description="site (a preset) or the user's id")
    kind: str | None = Field(description="strategy | screener (null when it does not resolve)")
    impl: str | None
    schedule: str | None
    selection: str | None = Field(description="the named selection, or inline")
    hash: str | None = Field(description="fingerprint of the resolved config")
    error: str | None = Field(description="why the config does not resolve")


class ConfigDetail(Schema):
    config_id: str
    user: str
    hash: str
    layers: list[str]
    resolved: dict[str, Any]
