"""``curate``: the owner's paraphrases become case files; a stored sentence is never copied (the
verbatim guard, ADR 0066), the criteria must validate and name no holding, the split is stable and
a case file is never overwritten."""

from datetime import date
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

TODAY = date(2026, 10, 11)
OTHER = ["watch gold miners with strong momentum lately"]  # a real sentence of another chain
REAL = ["Show me stocks with RSI under 30", "and also cheap on sales"]
FINAL = {"criteria": {"c1": {"field": "rollup.momentum@v1.rsi_14", "op": "lt", "value": 30}},
         "rank": None}  # fmt: skip


def stored(final: Any = FINAL) -> list[dict[str, Any]]:
    return [{
        "chain_id": "s1", "user": "u", "doc_id": "d", "source_event": "evt1",
        "source_events": ["r1", "evt1"],
        "sentences": [{"ts": 1, "sentence": REAL[0], "current_criteria": {"criteria": {}}},
                      {"ts": 2, "sentence": REAL[1], "current_criteria": FINAL}],
        "final_criteria": final,
    }]  # fmt: skip


def entry(**over: Any) -> dict[str, Any]:
    return {"source_event": "evt1",
            "sentences": ["oversold names, relative strength weak", "plus a valuation screen"],
            **over}  # fmt: skip


def planned_of(entries: Any, rows: Any, validate: Any, dest: Path, real: Any = OTHER) -> Any:
    return plan_cases(entries, rows, validate, dest, [*real], TODAY)


def ok(document: dict[str, Any]) -> None:
    assert document["kind"] == "screener" and document["criteria"]


def refuse(document: dict[str, Any]) -> None:
    raise ConfigurationError("x/y.criteria.c1.field: unknown field")


def test_a_curation_becomes_a_multi_sentence_case_with_no_recorded_answers(tmp_path: Path) -> None:
    (plan,) = planned_of([entry()], stored(), ok, tmp_path / "cases")
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
        planned_of([entry()], stored(), ok, tmp_path / "cases")
    with pytest.raises(FileExistsError):
        write_cases([plan])


def test_a_paraphrase_that_copies_a_real_sentence_is_refused(tmp_path: Path) -> None:
    assert verbatim_of("show me stocks with RSI under 30!", REAL) == REAL[0]  # same words
    assert verbatim_of("show me stocks with rsi under 30 today", REAL) == REAL[0]  # >= 0.8 shared
    assert verbatim_of("oversold names, weak relative strength", REAL) is None
    copy = entry(sentences=["show me stocks with RSI under 30.", "plus a valuation screen"])
    with pytest.raises(ConfigurationError, match="sentence 1 copies a real sentence"):
        planned_of([copy], stored(), ok, tmp_path)


def test_an_edge_chain_is_refused_whatever_its_shape(tmp_path: Path) -> None:
    rows = [{**stored()[0], "doc_kind": "edge"}]
    with pytest.raises(ConfigurationError, match="never a golden case"):
        planned_of([entry()], rows, ok, tmp_path)


def test_every_problem_is_reported_and_the_count_must_match(tmp_path: Path) -> None:
    bad = [entry(sentences=["just one"]), {"source_event": "nope", "sentences": ["x"]},
           entry(split="dev"), {"sentences": []}]  # fmt: skip
    with pytest.raises(ConfigurationError) as err:
        planned_of(bad, stored(), ok, tmp_path)
    text = str(err.value)
    for part in ("2 sentence(s) in the chain, 1 given", "not a candidate in range",
                 "split must be one of", "needs a source_event"):  # fmt: skip
        assert part in text
    with pytest.raises(ConfigurationError, match="non-empty list"):
        planned_of([], stored(), ok, tmp_path)


def test_criteria_must_validate_and_name_no_holding(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="not a valid rule screen"):
        planned_of([entry()], stored(), refuse, tmp_path)
    held = {
        "criteria": {"c1": {"field": "instrument.ticker", "op": "eq", "value": "EQ:BBG000B9XRY4"}}
    }
    with pytest.raises(ConfigurationError) as err:
        planned_of([entry(criteria=held)], stored(), ok, tmp_path)
    assert "names a position" in str(err.value) and "an instrument id" in str(err.value)
    with pytest.raises(ConfigurationError, match="no criteria table"):
        planned_of([entry()], stored({"truncated": True}), ok, tmp_path)


def test_the_owner_approved_criteria_replace_the_stored_ones(tmp_path: Path) -> None:
    mine = {"criteria": {"c1": {"field": "feature.pe_ratio", "op": "lt", "value": 15}}}
    (plan,) = planned_of([entry(criteria=mine, id="my-case", split="held_out")], stored(), ok,
                         tmp_path)  # fmt: skip
    assert plan.body["final_criteria"] == mine and plan.body["split"] == "held_out"
    assert plan.path.name == "my-case.json"


def test_the_split_is_stable_and_about_a_fifth_held_out() -> None:
    assert split_of("evt1") == split_of("evt1")
    held = sum(split_of(f"event-{n}") == "held_out" for n in range(1000))
    assert abs(held - 10 * HELD_OUT_PERCENT) < 60


def test_the_case_names_its_chain_and_waits_for_a_recording(tmp_path: Path) -> None:
    (plan_,) = planned_of([entry()], stored(), ok, tmp_path)
    body = plan_.body
    assert body["source_events"] == ["r1", "evt1"] and body["chain_id"] == "s1"
    assert body["curated"] == "2026-10-11" and body["recorded"] is False


def test_the_guard_checks_every_loaded_sentence_and_shared_five_word_runs(tmp_path: Path) -> None:
    other = entry(sentences=["watch gold miners with strong momentum lately!", "valuation extra"])
    with pytest.raises(ConfigurationError, match="sentence 1 copies"):
        planned_of([other], stored(), ok, tmp_path)  # a sentence of ANOTHER chain
    run = entry(sentences=["i want gold miners with strong momentum", "valuation extra"])
    with pytest.raises(ConfigurationError, match="sentence 1 copies"):
        planned_of([run], stored(), ok, tmp_path)  # five shared words, below the 0.8 overlap
    assert verbatim_of("gold miners with strong", OTHER) is None  # four words are fine


def test_holding_like_tokens_warn_and_are_still_written(tmp_path: Path) -> None:
    flagged = entry(sentences=["oversold names like NVDA 120 lately", "plus a valuation screen"],
                    criteria={"criteria": {"AAPL": {"field": "feature.sector", "op": "eq",
                                                      "value": "TSLA"}}})  # fmt: skip
    (plan_,) = planned_of([flagged], stored(), ok, tmp_path)
    text = "\n".join(describe([plan_]))
    assert "WARNING looks like a holding, still written: paraphrase 1: NVDA" in text
    assert any(w.startswith("criteria: AAPL") for w in plan_.warnings)
    assert "criteria value: TSLA" in plan_.warnings
    assert "in force at 2:" in text  # the criteria in force are shown to the owner


def test_a_clean_curation_has_no_warnings(tmp_path: Path) -> None:
    (plan_,) = planned_of([entry()], stored(), ok, tmp_path)
    assert plan_.warnings == ()
