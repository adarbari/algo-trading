"""``draft_screen`` (ADR 0041): the model's criteria become a valid draft; an invented field,
a bad op or value and one the validator rejects are dropped with their reason; the tie-break
and notes come through; the sentence is bounded; a model that cannot answer is unavailable;
nothing is written."""

import json
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.completion import Attempt, CallTag, Completion
from algotrade.core.model.errors import ConfigurationError, ModelUnavailableError
from algotrade.services.configs import resolve_rule_draft
from algotrade.services.drafting import screens
from algotrade.services.drafting.answer_schema import ANSWER_SCHEMA
from algotrade.services.drafting.prompt import PROMPT_VERSION
from algotrade.services.drafting.screens import (
    MAX_TEXT,
    DroppedCriterion,
    draft_screen,
    parse_answer,
)
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.text_model.chain import FallbackTextModel
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.screening.test_rule_screens import (
    ACTIVE as ACTIVE_SELECTION,
)
from tests.unit.services.screening.test_rule_screens import (
    DAY,
    LIQ,
    SCREEN,
    configs,
    seeded,
)

ALICE = "alice"
PRICE = f"{LIQ}.underlying_price"
OI = f"{LIQ}.chain_oi"


class Canned:
    """A ``TextModel`` with one answer; keeps what it was asked."""

    names = ("canned",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def __init__(self, answer: Any) -> None:
        self.answer = answer if isinstance(answer, str) else json.dumps(answer)
        self.asked: list[tuple[str, str]] = []
        self.tags: list[object] = []

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: object = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        self.asked.append((system, user))
        self.tags.append(tag)
        return Completion(self.answer, "canned", "canned")


class Down:
    names = ("down",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: object = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        raise ModelUnavailableError("llama at http://localhost:11434/v1: timed out")


@pytest.fixture
def ctx() -> ReadContext:
    reader, _ = seeded()
    return open_context(reader, configs(), UserContext(ALICE), DAY)


def proposal(*criteria: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"criteria": list(criteria), "tie_break": None, "notes": [], **extra}


ACTIVE = {"id": "active", "field": "instrument.status", "op": "eq", "value": "ACTIVE"}
PRICE_GT = {"id": "price", "field": PRICE, "op": "gt", "value": 50, "why": "over $50"}


def test_the_model_is_asked_as_the_drafting_user(ctx: ReadContext) -> None:
    model = Canned(proposal(ACTIVE))
    draft_screen(ctx, model, "my_screen", "active stocks")
    assert model.tags == [
        CallTag("screener-draft", ALICE, PROMPT_VERSION)
    ]  # who decides which providers answer


def test_the_answer_becomes_a_valid_draft(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            ACTIVE,
            PRICE_GT,
            {
                "id": "oi",
                "field": OI,
                "op": "gte",
                "value": 1000,
                "mode": "soft",
                "tolerance": {"relative": 0.5},
                "on_miss": "LIQUIDITY_RISK",
            },
            {
                "id": "kind",
                "field": "instrument.security_type",
                "op": "in",
                "value": ["COMMON_STOCK", "ADR"],
            },
            tie_break={"field": PRICE, "descending": False},
            notes=["assumed US dollars"],
        )
    )
    draft = draft_screen(ctx, model, "my_screen", "active stocks over $50 with open interest")
    assert (
        draft.screener_id == "my_screen"
        and draft.dropped == ()
        and draft.notes == ("assumed US dollars",)
    )
    doc = draft.document
    assert (doc["id"], doc["kind"], doc["impl"]) == ("my_screen", "screener", "rules")
    assert doc["criteria"] == {
        "active": {"field": "instrument.status", "op": "eq", "value": "ACTIVE"},
        "price": {"field": PRICE, "op": "gt", "value": 50},
        "oi": {
            "field": OI,
            "op": "gte",
            "value": 1000,
            "mode": "soft",
            "tolerance": {"relative": 0.5},
            "on_miss": "LIQUIDITY_RISK",
        },
        "kind": {"field": "instrument.security_type", "op": "in", "value": ["COMMON_STOCK", "ADR"]},
    }
    assert doc["rank"] == {"tie_break": PRICE, "tie_break_order": "asc"}
    resolve_rule_draft(ctx.configs, "my_screen", ctx.user, doc)  # as finalise validates
    system, user = model.asked[0]
    assert PRICE in system and "instrument.status" in system  # the catalogue
    assert user.endswith("Sentence: active stocks over $50 with open interest\n")


def test_invented_fields_bad_ops_and_bad_values_are_dropped_with_reasons(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            PRICE_GT,
            {
                "id": "iv",
                "field": "rollup.made_up@v9.iv_rank",
                "op": "gte",
                "value": 0.5,
                "why": "IV rank above 50%",
            },
            {"id": "weird", "field": PRICE, "op": "like", "value": 1},
            {"id": "range", "field": PRICE, "op": "between", "value": [1]},
            {"id": "mode", "field": PRICE, "op": "lt", "value": 9, "mode": "fuzzy"},
            tie_break={"field": "rollup.made_up@v9.iv_rank", "descending": True},
        )
    )
    draft = draft_screen(ctx, model, "s", "stocks over $50 with IV rank above 50%")
    assert set(draft.document["criteria"]) == {"price"} and "rank" not in draft.document
    assert draft.dropped == (
        DroppedCriterion(
            "iv",
            "rollup.made_up@v9.iv_rank",
            "field 'rollup.made_up@v9.iv_rank' is not in the catalogue (IV rank above 50%)",
        ),
        DroppedCriterion("weird", PRICE, "unknown op 'like'"),
        DroppedCriterion("range", PRICE, "between needs a list of two numbers"),
        DroppedCriterion("mode", PRICE, "unknown mode 'fuzzy'"),
    )


def test_a_criterion_the_validator_rejects_is_dropped_and_the_rest_kept(ctx: ReadContext) -> None:
    # A text comparison on a number: the catalogue has the field, the validator rejects the value.
    model = Canned(proposal(PRICE_GT, {"id": "bad", "field": PRICE, "op": "gt", "value": "high"}))
    draft = draft_screen(ctx, model, "s", "price over 50, high price")
    assert list(draft.document["criteria"]) == ["price"]
    (gone,) = draft.dropped
    assert gone.id == "bad" and gone.field == PRICE and "high" in gone.reason
    resolve_rule_draft(ctx.configs, "s", ctx.user, draft.document)


def test_an_empty_draft_when_nothing_maps(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            {"id": "x", "field": "feature.nope", "op": "gt", "value": 1}, notes=["no such field"]
        )
    )
    draft = draft_screen(ctx, model, "s", "something the catalogue lacks")
    assert draft.document["criteria"] == {} and len(draft.dropped) == 1
    assert draft.notes == ("no such field",)


def test_ids_are_slugs_and_unique(ctx: ReadContext) -> None:
    model = Canned(
        proposal(
            {"id": "not a slug!", "field": PRICE, "op": "gt", "value": 1},
            {"id": "underlying_price", "field": PRICE, "op": "lt", "value": 100},
            {"field": PRICE, "op": "gte", "value": 2},
        )
    )
    draft = draft_screen(ctx, model, "s", "price between")
    assert list(draft.document["criteria"]) == [
        "underlying_price",
        "underlying_price_2",
        "underlying_price_3",
    ]


def test_a_fenced_answer_is_read_and_a_non_draft_is_unavailable() -> None:
    assert parse_answer('```json\n{"criteria": []}\n```')["criteria"] == []
    with pytest.raises(ModelUnavailableError, match="not JSON"):
        parse_answer("Sure! Here is the screen: ...")
    with pytest.raises(ModelUnavailableError, match="no criteria"):
        parse_answer('{"screen": 1}')


def test_the_sentence_is_bounded_and_the_model_can_be_down(ctx: ReadContext) -> None:
    with pytest.raises(ConfigurationError, match="empty"):
        draft_screen(ctx, Canned(proposal()), "s", "   ")
    with pytest.raises(ConfigurationError, match=str(MAX_TEXT)):
        draft_screen(ctx, Canned(proposal()), "s", "x" * (MAX_TEXT + 1))
    with pytest.raises(ModelUnavailableError, match="timed out"):
        draft_screen(ctx, Down(), "s", "stocks")


def test_the_site_phrasebook_goes_to_the_model() -> None:
    reader, _ = seeded()
    phrasebook = {
        "phrase": [
            {"say": ["liquid"], "fields": [OI, "feature.nope"], "hint": "chain_oi gte 1000"},
            {"say": ["yield"], "fields": ["feature.nope"]},
        ]
    }
    store = MemoryConfigStore(
        {
            ("site", "selections", "active"): ACTIVE_SELECTION,
            ("site", "strategies", "big_liquid"): SCREEN,
            ("site", "settings", "phrasebook"): phrasebook,
        }
    )
    ctx = open_context(reader, store, UserContext(ALICE), DAY)
    model = Canned(proposal(PRICE_GT))
    draft_screen(ctx, model, "s", "liquid names over 50")
    system = model.asked[0][0]
    assert f"liquid | {OI} | chain_oi gte 1000" in system
    assert "\nyield | " not in system  # a phrase with none of the catalogue's fields is left out


def test_the_current_criteria_go_to_the_model(ctx: ReadContext) -> None:
    model = Canned(proposal(PRICE_GT))
    current = {"id": "s", "criteria": {"price": {"field": PRICE, "op": "gt", "value": 5}}}
    draft_screen(ctx, model, "s", "raise the price floor to 50", current)
    assert f'"price": {{"field": "{PRICE}", "op": "gt", "value": 5}}' in model.asked[0][1]


class Rejecting(Canned):
    """A ``Canned`` model that keeps what the caller rejected (as the chain would log it)."""

    def __init__(self, answer: Any) -> None:
        super().__init__(answer)
        self.rejected: list[tuple[object, Completion, str, str, int | None]] = []

    def reject(
        self, tag: object, completion: Completion, reason: str, user_text: str, chars: int | None
    ) -> None:
        self.rejected.append((tag, completion, reason, user_text, chars))


def test_an_answer_that_is_not_json_is_reported_rejected_with_the_prompt(ctx: ReadContext) -> None:
    model = Rejecting("Sure! Support lines are not in the catalogue.")
    with pytest.raises(ModelUnavailableError, match="not JSON"):
        draft_screen(ctx, model, "s", "stocks near support")
    ((tag, completion, reason, user_text, chars),) = model.rejected
    assert tag == CallTag("screener-draft", ALICE, PROMPT_VERSION)
    assert completion.text.startswith("Sure! Support")
    assert reason == "the model's answer is not JSON"
    assert user_text == model.asked[0][1] and "stocks near support" in user_text
    assert chars == len(model.asked[0][0]) + len(model.asked[0][1])


def test_an_answer_with_no_criteria_list_is_rejected_and_a_usable_one_is_not(
    ctx: ReadContext,
) -> None:
    model = Rejecting('{"screen": 1}')
    with pytest.raises(ModelUnavailableError, match="no criteria"):
        draft_screen(ctx, model, "s", "anything")
    assert [r[2] for r in model.rejected] == ["the model's answer has no criteria list"]
    fine = Rejecting(proposal())
    draft_screen(ctx, fine, "s", "anything")
    assert fine.rejected == []


def test_a_model_that_cannot_report_a_rejection_is_unaffected(ctx: ReadContext) -> None:
    with pytest.raises(ModelUnavailableError, match="not JSON"):
        draft_screen(ctx, Canned("nope"), "s", "anything")  # no ``reject``: ignored


def test_a_draft_the_validator_refuses_is_reported_rejected_and_still_raises(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise ConfigurationError("s.rank: unknown tie_break")

    monkeypatch.setattr("algotrade.services.drafting.screens.validated", refuse)
    model = Rejecting(proposal())
    with pytest.raises(ConfigurationError, match="unknown tie_break"):
        draft_screen(ctx, model, "s", "anything")
    assert [r[2] for r in model.rejected] == ["s.rank: unknown tie_break"]


def test_a_reject_that_breaks_never_masks_the_draft_error(ctx: ReadContext) -> None:
    class Breaking(Rejecting):
        def reject(self, *args: Any) -> None:  # type: ignore[override]
            raise RuntimeError("ledger down")

    with pytest.raises(ModelUnavailableError, match="not JSON"):
        draft_screen(ctx, Breaking("nope"), "s", "anything")


# --------------------------- through the chain: schema, validate, repair once, escalate


class Scripted:
    """A provider that gives its answers in order; keeps the stage and schema of each call."""

    def __init__(self, provider: str, *answers: str) -> None:
        self.provider, self.answers = provider, list(answers)
        self.names = (provider,)
        self.calls: list[tuple[str, str | None, object]] = []

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: CallTag | None = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        self.calls.append((user, tag.stage if tag else None, schema))
        return Completion(self.answers.pop(0), self.provider, self.provider)


class Ledger:
    def __init__(self) -> None:
        self.attempts: list[Attempt] = []

    def refuses(self) -> bool:
        return False

    def spends(self, provider: str) -> bool:
        return False

    def admit(self, provider: str, prompt_chars: int) -> float | None:
        return 0.0

    def record(self, attempt: Attempt, reserved: float = 0.0) -> None:
        self.attempts.append(attempt)


GOOD = json.dumps(proposal(PRICE_GT))
NOT_JSON = "Sure! Here is the screen."
WRONG_SHAPE = json.dumps({"criteria": {"field": PRICE}})


def chained(ledger: Ledger, *members: Scripted) -> FallbackTextModel:
    return FallbackTextModel([(m.provider, m) for m in members], ledger=ledger)


def test_a_valid_first_answer_is_one_call_asked_with_the_schema(ctx: ReadContext) -> None:
    cheap, strong = Scripted("cheap", GOOD), Scripted("strong")
    draft = draft_screen(ctx, chained(Ledger(), cheap, strong), "s", "over $50")
    assert list(draft.document["criteria"]) == ["price"]
    assert [(stage, schema) for _, stage, schema in cheap.calls] == [("first", ANSWER_SCHEMA)]
    assert not strong.calls


def test_an_answer_that_is_not_json_is_repaired_by_the_same_provider(ctx: ReadContext) -> None:
    cheap, strong = Scripted("cheap", NOT_JSON, GOOD), Scripted("strong")
    ledger = Ledger()
    draft = draft_screen(ctx, chained(ledger, cheap, strong), "s", "over $50")
    assert list(draft.document["criteria"]) == ["price"]
    assert [stage for _, stage, _ in cheap.calls] == ["first", "repair"] and not strong.calls
    assert "Your answer was rejected: the model's answer is not JSON." in cheap.calls[1][0]
    assert NOT_JSON in cheap.calls[1][0]
    assert [(a.outcome, a.call_stage) for a in ledger.attempts] == [
        ("ok", "first"), ("rejected", "first"), ("ok", "repair")]  # fmt: skip


def test_invalid_twice_escalates_and_a_schema_breach_counts_as_invalid(ctx: ReadContext) -> None:
    cheap, strong = Scripted("cheap", WRONG_SHAPE, NOT_JSON), Scripted("strong", GOOD)
    ledger = Ledger()
    draft = draft_screen(ctx, chained(ledger, cheap, strong), "s", "over $50")
    assert list(draft.document["criteria"]) == ["price"]
    assert [s for _, s, _ in cheap.calls] == ["first", "repair"]
    assert [s for _, s, _ in strong.calls] == ["escalate"]
    assert "has no criteria list" in cheap.calls[1][0]
    rejected = [a for a in ledger.attempts if a.outcome == "rejected"]
    assert [a.answer for a in rejected] == [WRONG_SHAPE, NOT_JSON]
    assert (
        ledger.attempts[-1].outcome == "fell_back" and ledger.attempts[-1].call_stage == "escalate"
    )


def test_every_provider_failing_validation_lists_the_causes_after_two_calls_each(
    ctx: ReadContext,
) -> None:
    a, b = Scripted("a", NOT_JSON, NOT_JSON), Scripted("b", WRONG_SHAPE, WRONG_SHAPE)
    with pytest.raises(ModelUnavailableError) as raised:
        draft_screen(ctx, chained(Ledger(), a, b), "s", "over $50")
    assert "not JSON" in str(raised.value) and "no criteria list" in str(raised.value)
    assert len(a.calls) == len(b.calls) == 2


def test_a_draft_the_validator_refuses_is_repaired_too(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, refusals = screens.validated, ["s.rank: unknown tie_break"]

    def refuse_once(*args: Any, **kwargs: Any) -> Any:
        if refusals:
            raise ConfigurationError(refusals.pop())
        return real(*args, **kwargs)

    monkeypatch.setattr(screens, "validated", refuse_once)
    cheap = Scripted("cheap", GOOD, GOOD)
    draft = draft_screen(ctx, chained(Ledger(), cheap), "s", "over $50")
    assert list(draft.document["criteria"]) == ["price"]
    assert [s for _, s, _ in cheap.calls] == ["first", "repair"]
    assert "Your answer was rejected: s.rank: unknown tie_break." in cheap.calls[1][0]


def test_a_criterion_that_breaks_the_schema_is_dropped_with_its_reason_not_the_answer(
    ctx: ReadContext,
) -> None:
    answer = proposal(
        PRICE_GT,
        {"id": "tol", "field": PRICE, "op": "lt", "value": 9, "mode": "soft", "tolerance": "wide"},
        {"id": "obj", "field": OI, "op": "gte", "value": {"n": 1}},
    )
    only = Scripted("only", json.dumps(answer))
    draft = draft_screen(ctx, chained(Ledger(), only), "s", "over $50")
    assert list(draft.document["criteria"]) == ["price"] and len(only.calls) == 1  # no repair
    assert [(d.id, "not the criterion shape" in d.reason) for d in draft.dropped] == [
        ("tol", True), ("obj", True)]  # fmt: skip
    assert "tolerance" in draft.dropped[0].reason and "value" in draft.dropped[1].reason


def test_a_draft_carries_the_one_call_id_of_every_attempt_repair_and_escalation_included(
    ctx: ReadContext,
) -> None:
    ledger = Ledger()
    model = chained(ledger, Scripted("cheap", NOT_JSON, NOT_JSON), Scripted("strong", GOOD))
    draft = draft_screen(ctx, model, "s", "over $50")
    ids = {a.call_id for a in ledger.attempts}
    assert len(ledger.attempts) == 5 and ids == {draft.call_id} and draft.call_id
