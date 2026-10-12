"""The cap and the usage log together (owner decision 2026-10-12: only a call that returned a draft
counts): a real provider chain with its ledger writes the calls to a store as the API's recorder
does, and a cap over that store, as after a restart, counts a re-draft that was merged and not one
whose merge failed after the model had answered (the answer is rejected in the log, so the call
nets to nothing)."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from algotrade.config.site.llm import LlmSettings
from algotrade.core.model.completion import Completion
from algotrade.core.model.errors import ConfigurationError, DailyLimitError
from algotrade.core.time.calendar import exchange_date
from algotrade.data import StoreReader
from algotrade.data.usage import calls_of
from algotrade.services.drafting.redraft import run
from algotrade.services.drafting.redraft.cap import USE_CASE, PartRedraftCap
from algotrade.services.drafting.redraft.request import check_request
from algotrade.services.read.context import ReadContext
from algotrade.services.text_model.chain import FallbackTextModel
from algotrade.services.text_model.ledger import UsageLedger
from algotrade.services.text_model.usage import UsageRecorder
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.usage_writer import UsageWriter
from tests.helpers.drafting.redraft import answer_for, body_of, held_draft
from tests.unit.services.drafting.redraft.test_run import PRICE_80
from tests.unit.services.drafting.test_screens import ALICE, ctx  # noqa: F401  (the fixture)


class Member:
    """The one provider of the chain: gives a fixed answer."""

    names = ("m",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def __init__(self, answer: Any) -> None:
        self.answer = json.dumps(answer)

    def complete(self, system: str, user: str, **_: object) -> Completion:
        return Completion(self.answer, "m", "default", 10, 5, 0.1)


class Log:
    """A chain with a real ledger writing to a store through the recorder, and a reader of it."""

    def __init__(self, answer: Any) -> None:
        self.backend = MemoryBackend()
        self.recorder = UsageRecorder(UsageWriter(self.backend))
        self.model = FallbackTextModel(
            [("default", Member(answer))], ledger=UsageLedger(LlmSettings(), self.recorder)
        )
        self.reader = StoreReader(self.backend)

    def counted(self) -> set[str]:
        self.recorder.flush()  # the background write has landed
        return calls_of(self.reader, exchange_date(datetime.now(UTC)), USE_CASE, ALICE)


@pytest.fixture
def log() -> Iterator[Log]:
    made = Log(answer_for("over $80", PRICE_80, reading="Price above $80"))
    yield made
    made.recorder.close()


def retype(ctx: ReadContext, log: Log, cap: PartRedraftCap) -> Any:  # noqa: F811
    request = check_request("my_screen", body_of(held_draft(ctx), "p2", "over $80"))
    with cap.slot(ALICE) as slot:
        return run.redraft_part(ctx, log.model, request, slot.note)


def test_a_merged_re_draft_is_in_the_log_and_counts_after_a_restart(
    ctx: ReadContext,  # noqa: F811
    log: Log,
) -> None:
    done = retype(ctx, log, PartRedraftCap(log.reader, lambda: 1))
    assert done.draft.call_id in log.counted()
    restarted = PartRedraftCap(log.reader, lambda: 1)  # no memory of its own
    with pytest.raises(DailyLimitError), restarted.slot(ALICE):
        pass


def test_a_merge_that_fails_after_the_model_answered_does_not_count_even_from_the_log(
    ctx: ReadContext,  # noqa: F811
    log: Log,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(*_: object) -> None:
        raise ConfigurationError("the merge could not hold together")

    monkeypatch.setattr(run, "merge_part", failing)
    with pytest.raises(ConfigurationError, match="could not hold together"):
        retype(ctx, log, PartRedraftCap(log.reader, lambda: 1))
    assert log.counted() == set()  # the call is in the log, answered and then rejected: nets zero
    restarted = PartRedraftCap(log.reader, lambda: 1)
    with restarted.slot(ALICE):  # the place is free, from memory and from the log
        pass
