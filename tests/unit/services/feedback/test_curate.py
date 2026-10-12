"""``curate``: the owner's paraphrases become case files; a stored sentence is never copied (the
verbatim guard, ADR 0066), the criteria must validate and name no holding, the split is stable and
a case file is never overwritten."""

from pathlib import Path
from typing import Any

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.services.feedback.curate import (
    HELD_OUT_PERCENT,
    case_id,
    describe,
    plan_cases,
    split_of,
    verbatim_of,
    write_cases,
)

REAL = ["Show me stocks with RSI under 30", "and also cheap on sales"]
FINAL = {"criteria": {"c1": {"field": "rollup.momentum@v1.rsi_14", "op": "lt", "value": 30}},
         "rank": None}  # fmt: skip


def stored(final: Any = FINAL) -> list[dict[str, Any]]:
    return [{
        "chain_id": "s1", "user": "u", "doc_id": "d", "source_event": "evt1",
        "sentences": [{"ts": 1, "sentence": REAL[0], "current_criteria": {"criteria": {}}},
                      {"ts": 2, "sentence": REAL[1], "current_criteria": FINAL}],
        "final_criteria": final,
    }]  # fmt: skip


def entry(**over: Any) -> dict[str, Any]:
    return {"source_event": "evt1",
            "sentences": ["oversold names, relative strength weak", "plus a valuation screen"],
            **over}  # fmt: skip


def ok(document: dict[str, Any]) -> None:
    assert document["kind"] == "screener" and document["criteria"]


def refuse(document: dict[str, Any]) -> None:
    raise ConfigurationError("x/y.criteria.c1.field: unknown field")


def test_a_curation_becomes_a_multi_sentence_case_with_no_recorded_answers(tmp_path: Path) -> None:
    (plan,) = plan_cases([entry()], stored(), ok, tmp_path / "cases")
    assert plan.path == tmp_path / "cases" / f"{case_id('evt1')}.json"
    body = plan.body
    assert body["sentences"] == entry()["sentences"] and body["sentence"] == body["sentences"][-1]
    assert body["source_event"] == "evt1" and body["final_criteria"] == FINAL
    assert body["criteria_in_force"] == [{"criteria": {}}, FINAL]
    (part,) = body["expect"]["parts"]
    assert (part["fields"], part["op"], part["value"]) == (["rollup.momentum@v1.rsi_14"], "lt", 30)
    assert REAL[0] not in str(body) and "cases" in describe([plan])[0]
    assert write_cases([plan]) == [plan.path] and plan.path.exists()
    with pytest.raises(ConfigurationError, match="never overwritten"):
        plan_cases([entry()], stored(), ok, tmp_path / "cases")
    with pytest.raises(FileExistsError):
        write_cases([plan])


def test_a_paraphrase_that_copies_a_real_sentence_is_refused(tmp_path: Path) -> None:
    assert verbatim_of("show me stocks with RSI under 30!", REAL) == REAL[0]  # same words
    assert verbatim_of("show me stocks with rsi under 30 today", REAL) == REAL[0]  # >= 0.8 shared
    assert verbatim_of("oversold names, weak relative strength", REAL) is None
    copy = entry(sentences=["show me stocks with RSI under 30.", "plus a valuation screen"])
    with pytest.raises(ConfigurationError, match="sentence 1 copies a real sentence"):
        plan_cases([copy], stored(), ok, tmp_path)


def test_every_problem_is_reported_and_the_count_must_match(tmp_path: Path) -> None:
    bad = [entry(sentences=["just one"]), {"source_event": "nope", "sentences": ["x"]},
           entry(split="dev"), {"sentences": []}]  # fmt: skip
    with pytest.raises(ConfigurationError) as err:
        plan_cases(bad, stored(), ok, tmp_path)
    text = str(err.value)
    for part in ("2 sentence(s) in the chain, 1 paraphrased", "not a candidate in range",
                 "split must be one of", "needs a source_event"):  # fmt: skip
        assert part in text
    with pytest.raises(ConfigurationError, match="non-empty list"):
        plan_cases([], stored(), ok, tmp_path)


def test_criteria_must_validate_and_name_no_holding(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="not a valid rule screen"):
        plan_cases([entry()], stored(), refuse, tmp_path)
    held = {
        "criteria": {"c1": {"field": "instrument.ticker", "op": "eq", "value": "EQ:BBG000B9XRY4"}}
    }
    with pytest.raises(ConfigurationError) as err:
        plan_cases([entry(criteria=held)], stored(), ok, tmp_path)
    assert "names a position" in str(err.value) and "an instrument id" in str(err.value)
    with pytest.raises(ConfigurationError, match="no criteria table"):
        plan_cases([entry()], stored({"truncated": True}), ok, tmp_path)


def test_the_owner_approved_criteria_replace_the_stored_ones(tmp_path: Path) -> None:
    mine = {"criteria": {"c1": {"field": "feature.pe_ratio", "op": "lt", "value": 15}}}
    (plan,) = plan_cases([entry(criteria=mine, id="my-case", split="held_out")], stored(), ok,
                         tmp_path)  # fmt: skip
    assert plan.body["final_criteria"] == mine and plan.body["split"] == "held_out"
    assert plan.path.name == "my-case.json"


def test_the_split_is_stable_and_about_a_fifth_held_out() -> None:
    assert split_of("evt1") == split_of("evt1")
    held = sum(split_of(f"event-{n}") == "held_out" for n in range(1000))
    assert abs(held - 10 * HELD_OUT_PERCENT) < 60
