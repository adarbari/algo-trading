"""Shared pieces of the explaining tests: the regime of ``regime_ctx`` (STRESS on 1 Oct, the
``curve`` card on and changed, ``trend`` off, ``vix`` and ``hy`` unknown) and a model that
answers with what it was given."""

import json
from typing import Any

import pytest

from algotrade.core.model.completion import Completion
from algotrade.core.model.errors import ModelUnavailableError
from algotrade.services.read.regime.regime import MarketRegime, load_regime
from tests.unit.services.read.regime.conftest import regime_ctx


@pytest.fixture
def regime() -> MarketRegime:
    return load_regime(regime_ctx())


class Canned:
    """A ``TextModel`` with one answer (a JSON envelope for a dict); keeps what it was asked."""

    names = ("canned",)

    def __init__(self, answer: Any) -> None:
        self.answer = answer if isinstance(answer, str) else json.dumps(answer)
        self.asked: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> Completion:
        self.asked.append((system, user))
        return Completion(self.answer, "canned", "canned")


class Down:
    names = ("down",)

    def complete(self, system: str, user: str) -> Completion:
        raise ModelUnavailableError("llama at http://localhost:11434/v1: timed out")
