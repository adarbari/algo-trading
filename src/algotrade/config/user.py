"""Who a run belongs to. Phase 0: a plain validated label; identity/auth comes later."""

from dataclasses import dataclass

from algotrade.core.model.ids import validate_id

DEFAULT_USER = "local"
SITE_USER = "site"  # runs scheduled from shared site presets

__all__ = ["DEFAULT_USER", "SITE_USER", "UserContext", "validate_id"]


@dataclass(frozen=True)
class UserContext:
    user_id: str = DEFAULT_USER

    def __post_init__(self) -> None:
        validate_id("user", self.user_id)
