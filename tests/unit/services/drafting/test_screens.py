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
from algotrade.services.configs import field_catalog, resolve_rule_draft
from algotrade.services.drafting import formulas as formulas_module
from algotrade.services.drafting import screens
from algotrade.services.drafting.answer_schema import ANSWER_SCHEMA
from algotrade.services.drafting.prompt import PROMPT_VERSION
from algotrade.services.drafting.screens import (
    MAX_TEXT,
    DroppedCriterion,
    criteria_of,
    did_you_mean_candidates,
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
    assert f"{LIQ}.*\n" in system and "\nunderlying_price|" in system  # the indexed catalogue
    assert "instrument.*\n" in system and "\nstatus|" in system
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
            "not_in_catalogue",
            "not_in_catalogue: criteria[1]",
        ),
        DroppedCriterion("weird", PRICE, "unknown op 'like'", "bad_op", "bad_op: criteria[2]"),
        DroppedCriterion(
            "range",
            PRICE,
            "between needs a list of two numbers",
            "bad_value",
            "bad_value: criteria[3]",
        ),
        DroppedCriterion(
            "mode", PRICE, "unknown mode 'fuzzy'", "bad_mode", "bad_mode: criteria[4]"
        ),
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


FORMULA = {
    "name": "draft_oi_per_dollar",
    "expr": "option_liquidity.chain_oi / option_liquidity.underlying_price",
    "dtype": "float",
    "unit": "ratio",
    "description": "open interest per dollar of price",
    "null_meaning": "no price",
    "inputs": ["option_liquidity.chain_oi", "option_liquidity.underlying_price"],
    "criterion": {"op": "gt", "value": 20, "mode": None, "tolerance": None},
}
READINGS = {
    "term": "deep",
    "span": "deep",
    "default_index": 1,
    "alternatives": [
        {"label": "50", "criterion": {"id": None, "field": OI, "op": "gte", "value": 50}},
        {"label": "1000", "criterion": {"id": None, "field": OI, "op": "gte", "value": 1000}},
    ],
}
GAP = {
    "key": None, "new_key_slug": "oi_history", "span": "for a year", "description": "d",
    "why_needed": "w", "closest": [OI], "feasibility": "ROLLUP_FROM_STORED",
}  # fmt: skip


def test_the_contract_keys_come_through_and_the_document_holds_only_a_criteria() -> None:
    reader, _ = seeded()
    ctx = open_context(reader, configs(), UserContext(ALICE), DAY)
    model = Canned(proposal(ACTIVE, formulas=[FORMULA], missing=[GAP], unresolved=[READINGS]))
    draft = draft_screen(ctx, model, "my_screen", "deep oi per dollar for a year")
    (formula,) = draft.formulas
    assert formula.name == "draft_oi_per_dollar" and formula.pending
    assert formula.dry_run.session == DAY and formula.dry_run.criterion_pass == 2
    assert formula.criterion == {"field": "feature.draft_oi_per_dollar", "op": "gt", "value": 20}
    assert draft.formulas_dropped == ()
    assert [(m.key, m.new_key_slug, m.closest) for m in draft.missing] == [
        (None, "oi_history", (OI,))
    ]
    (term,) = draft.unresolved
    assert term.default_index == 1 and len(term.alternatives) == 2
    criteria = draft.document["criteria"]
    assert set(criteria) == {"active", "deep"}  # the default reading, no pending formula
    assert criteria["deep"] == {"field": OI, "op": "gte", "value": 1000}
    assert "draft_oi_per_dollar" not in json.dumps(draft.document)
    resolve_rule_draft(ctx.configs, "my_screen", ctx.user, draft.document)  # a valid document


def test_an_old_answer_has_no_contract_output(ctx: ReadContext) -> None:
    draft = draft_screen(ctx, Canned(proposal(ACTIVE)), "my_screen", "active")
    assert (draft.formulas, draft.formulas_dropped, draft.missing, draft.unresolved) == (
        (),
        (),
        (),
        (),
    )


def test_a_dropped_formula_and_an_unusable_alternative_are_said(ctx: ReadContext) -> None:
    bad = {**FORMULA, "name": "no_prefix"}
    one_alternative = {**READINGS, "alternatives": READINGS["alternatives"][:1]}
    draft = draft_screen(
        ctx, Canned(proposal(ACTIVE, formulas=[bad], unresolved=[one_alternative])), "s", "x"
    )
    assert draft.formulas == () and draft.formulas_dropped[0].name == "no_prefix"
    assert "draft_" in draft.formulas_dropped[0].reason
    assert draft.unresolved == () and "fewer than 2" in draft.notes[0]
    assert set(draft.document["criteria"]) == {"active"}


def test_an_alternative_the_validator_would_reject_is_not_offered(ctx: ReadContext) -> None:
    wrong_type = {"id": None, "field": OI, "op": "gte", "value": "lots"}
    first, last = READINGS["alternatives"]
    reading = {
        **READINGS,
        "alternatives": [first, {"label": "x", "criterion": wrong_type}, last],
        "default_index": 2,
    }
    draft = draft_screen(ctx, Canned(proposal(ACTIVE, unresolved=[reading])), "s", "x")
    (term,) = draft.unresolved
    assert [a.text for a in term.alternatives] == ["50", "1000"] and term.default_index == 1


class Retrying(Canned):
    """A model whose chain checks the answer twice (a repair, then a fallback) before returning."""

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: object = None,
        schema: object = None,
        accept: Any = None,
    ) -> Completion:
        for _ in range(2):
            accept(self.answer)
        return super().complete(system, user, tag=tag, schema=schema, accept=accept)


def test_the_dry_runs_are_made_once_on_the_accepted_draft_and_capped(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs: list[str] = []
    real = formulas_module.dry_run

    def counted(c: Any, definition: Any, criterion: Any = None) -> Any:
        runs.append(definition.name)
        return real(c, definition, criterion)

    monkeypatch.setattr(formulas_module, "dry_run", counted)
    many = [
        {**FORMULA, "name": f"draft_f{n}", "expr": f"option_liquidity.chain_oi * {n + 1}",
         "inputs": ["option_liquidity.chain_oi"]}
        for n in range(10)
    ]  # fmt: skip
    draft = draft_screen(ctx, Retrying(proposal(ACTIVE, formulas=many)), "s", "x")
    assert runs == ["draft_f0", "draft_f1", "draft_f2"]  # not once per attempt, not ten
    assert all(f.dry_run.session == DAY for f in draft.formulas)
    assert any("7 formulas beyond the first 3 were cut" in n for n in draft.notes)


def test_a_default_the_model_also_listed_is_not_added_twice(ctx: ReadContext) -> None:
    listed = {"id": "deep_oi", "field": OI, "op": "gte", "value": 1000}
    draft = draft_screen(ctx, Canned(proposal(ACTIVE, listed, unresolved=[READINGS])), "s", "x")
    assert set(draft.document["criteria"]) == {"active", "deep_oi"}
    assert draft.unresolved[0].default_index == 1


def test_a_default_the_validator_dropped_is_not_still_the_default(
    ctx: ReadContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def drops_deep(c: Any, sid: str, document: dict[str, Any], dropped: Any) -> Any:
        kept = {k: v for k, v in document["criteria"].items() if k != "deep"}
        return {**document, "criteria": kept}, dropped

    monkeypatch.setattr(screens, "validated", drops_deep)
    draft = draft_screen(ctx, Canned(proposal(ACTIVE, unresolved=[READINGS])), "s", "x")
    assert draft.unresolved[0].default_index == 0
    assert "the validator dropped its default reading" in draft.notes[-1]


BARE = "underlying_price"  # the index entry under ``rollup.option_liquidity@v1.*``, no heading


def test_a_bare_entry_name_is_dropped_with_the_full_candidates(ctx: ReadContext) -> None:
    catalogue = set(field_catalog(ctx.configs).fields)
    criteria, dropped = criteria_of(
        {"criteria": [{"id": "p", "field": BARE, "op": "gt", "value": 50}]}, catalogue
    )
    assert not criteria and dropped[0].field == BARE
    assert f"did you mean `{PRICE}`" in dropped[0].reason
    assert (
        "did you mean"
        not in criteria_of(
            {"criteria": [{"id": "p", "field": "made_up_thing", "op": "gt", "value": 5}]}, catalogue
        )[1][0].reason
    )  # no candidate: a plain drop
    assert did_you_mean_candidates("rollup.made_up@v9.underlying_price", catalogue) == []


def test_a_bare_entry_name_is_repaired_with_the_full_name_in_the_ask(ctx: ReadContext) -> None:
    bare = json.dumps(proposal({"id": "price", "field": BARE, "op": "gt", "value": 50}))
    cheap = Scripted("cheap", bare, GOOD)
    draft = draft_screen(ctx, chained(Ledger(), cheap), "s", "over $50")
    assert [s for _, s, _ in cheap.calls] == ["first", "repair"]
    assert f"`{PRICE}`" in cheap.calls[1][0]  # the repair names the full field
    assert draft.document["criteria"]["price"]["field"] == PRICE and not draft.dropped


def test_bare_names_in_every_attempt_keep_the_good_criteria_and_other_problems_still_fail(
    ctx: ReadContext,
) -> None:
    bare = {"id": "bare", "field": BARE, "op": "gt", "value": 50}
    answer = json.dumps(proposal(PRICE_GT, bare))
    only = Scripted("only", answer, answer)  # the first answer and the repair
    draft = draft_screen(ctx, chained(Ledger(), only), "s", "over $50")
    assert [s for _, s, _ in only.calls] == ["first", "repair"]
    assert list(draft.document["criteria"]) == ["price"]
    assert [(d.id, d.field) for d in draft.dropped] == [("bare", BARE)]
    assert f"did you mean `{PRICE}`" in draft.dropped[0].reason
    other = {"id": "made", "field": "rollup.made_up@v9.x", "op": "gt", "value": 1}
    mixed = json.dumps(proposal(PRICE_GT, bare, other))
    with pytest.raises(ModelUnavailableError):
        draft_screen(ctx, chained(Ledger(), Scripted("m", mixed, mixed)), "s", "over $50")


def sug(**over: Any) -> dict[str, Any]:
    base = {
        "field": OI, "op": "gte", "value": 1000, "mode": "score", "tolerance": None,
        "on_miss": None, "why": "thin open interest hides the spread", "source": PRICE,
    }  # fmt: skip
    return {**base, **over}


def test_suggestions_are_offered_beside_the_document_never_in_it(ctx: ReadContext) -> None:
    answer = proposal(
        ACTIVE, PRICE_GT,
        suggestions=[
            sug(), sug(field=PRICE, op="gt", value=50), sug(mode="hard", value=7),
            sug(field="nope.x"),
            sug(field=OI, op="gte", value=500, mode="soft", tolerance=100, on_miss="EVENT_RISK"),
        ],
    )  # fmt: skip
    draft = draft_screen(ctx, Canned(answer), "my_screen", "over $50")
    assert set(draft.document["criteria"]) == {"active", "price"}
    assert [(s.criterion["field"], s.criterion["mode"], s.source) for s in draft.suggestions] == [
        (OI, "score", PRICE),
        (OI, "soft", PRICE),
    ]
    assert draft.suggestions[1].criterion["on_miss"] == "EVENT_RISK"
    assert [d.field for d in draft.suggestions_dropped] == [OI, "nope.x"]  # hard, then invented
    resolve_rule_draft(ctx.configs, "my_screen", ctx.user, draft.document)


def test_a_soft_suggestion_without_a_tolerance_is_refused_by_the_criterion_validator(
    ctx: ReadContext,
) -> None:
    draft = draft_screen(ctx, Canned(proposal(ACTIVE, suggestions=[sug(mode="soft")])), "s", "x")
    assert draft.suggestions == () and "tolerance" in draft.suggestions_dropped[0].reason


def test_an_answer_without_suggestions_offers_none(ctx: ReadContext) -> None:
    draft = draft_screen(ctx, Canned(proposal(ACTIVE)), "my_screen", "active")
    assert (draft.suggestions, draft.suggestions_dropped) == ((), ())


def test_a_suggestion_equal_to_a_non_default_alternative_is_not_offered_twice(
    ctx: ReadContext,
) -> None:
    other = {"label": "price", "criterion": {"id": None, "field": PRICE, "op": "gt", "value": 50}}
    term = {**READINGS, "alternatives": [READINGS["alternatives"][1], other], "default_index": 0}
    answer = proposal(
        ACTIVE, unresolved=[term],
        suggestions=[
            sug(field=PRICE, op="gt", value=50, mode="score"), sug(field=OI, op="lt", value=9),
        ],
    )  # fmt: skip
    draft = draft_screen(ctx, Canned(answer), "my_screen", "deep")
    assert [(s.criterion["field"], s.criterion["op"]) for s in draft.suggestions] == [(OI, "lt")]
    assert draft.suggestions_dropped == ()
