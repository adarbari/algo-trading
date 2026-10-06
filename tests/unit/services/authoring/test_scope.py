"""Whose configs a write touches: a valid id, never the site, and a user the registry declares
(ADR 0040)."""

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.authoring.scope import author


def test_a_declared_user_is_the_author() -> None:
    assert author("alice", lambda user: user == "alice").user_id == "alice"
    assert author("anyone").user_id == "anyone"  # no registry given: the id rules only


@pytest.mark.parametrize("user", ["mallory", "bob"])
def test_an_undeclared_user_is_refused(user: str) -> None:
    with pytest.raises(ConfigurationError, match="unknown user"):
        author(user, lambda declared: declared == "alice")


@pytest.mark.parametrize("user", ["site", "../etc", "Alice", ""])
def test_the_site_and_invalid_ids_are_refused_even_when_declared(user: str) -> None:
    with pytest.raises(ConfigurationError):
        author(user, lambda declared: True)
