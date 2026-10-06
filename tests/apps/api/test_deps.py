"""Request dependencies: whose configs a request is for (``acting_for``, ADR 0040)."""

import pytest
from fastapi import HTTPException

from algotrade.config.site.users import Role, UserRecord
from algotrade_api.deps import acting_for

TOM = UserRecord("tom", Role.TRADER)
ANA = UserRecord("ana", Role.ADMIN)


def test_a_request_is_for_the_caller_by_default() -> None:
    assert acting_for(TOM, None) == "tom" and acting_for(TOM, "tom") == "tom"


def test_only_an_admin_acts_for_another_user() -> None:
    assert acting_for(ANA, "tom") == "tom"
    with pytest.raises(HTTPException) as raised:
        acting_for(TOM, "ana")
    assert raised.value.status_code == 403
