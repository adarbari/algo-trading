"""``algotrade-api golden judge`` (``judge.py``, ``judge_prompt.py``): the rubric parse, a repaired
invalid verdict, aggregation and patterns, the guard rails and the plan, with fake models (CI
never calls the network)."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import (
    ConfigurationError,
    InvalidAnswerError,
    ModelUnavailableError,
)
from algotrade.services.drafting.contract.formulas import DraftFormula
from algotrade.services.drafting.contract.gaps import MissingFeature, Unresolved
from algotrade.services.drafting.golden.golden_run import CostTap
from algotrade.services.drafting.golden.judge import (
    JudgeArgs,
    Judged,
    JudgeRun,
    judge_once,
    make_judge_plan,
    measure,
    report,
    report_lines,
    run_golden_judge,
    run_judge,
    top_patterns,
)
from algotrade.services.drafting.golden.judge_prompt import (
    JUDGE_SCHEMA,
    Issue,
    judge_user_prompt,
    parse_verdict,
    render_draft,
)
from algotrade.services.drafting.parts.model import Part
from algotrade.services.drafting.screens import DroppedCriterion, ScreenDraft
from algotrade.services.text_model.model import TextModel
from tests.unit.services.drafting.golden.test_golden_run import (
    LLM,
    Harness,
    Scripted,
    case,
    draft,
    write_case,
)

PERFECT = json.dumps({"segmentation": 2, "coverage": 2, "logic": 2, "fidelity": 2, "issues": []})
FLAWED = json.dumps(
    {
        "segmentation": 0, "coverage": 2, "logic": 1, "fidelity": 2,
        "issues": [
            {"dimension": "segmentation", "pattern": "connector-chip", "detail": "'but' is a chip"},
            {"dimension": "logic", "pattern": "or-as-and", "detail": "or became two criteria"},
        ],
    }
)  # fmt: skip


def screen(**over: Any) -> ScreenDraft:
    part = Part(
        "p1", "iv rank above 50", 0, 16, "IV rank > 50", "model", "condition", "model", ("c1",)
    )
    base: dict[str, Any] = {
        "screener_id": "g",
        "document": {
            "criteria": {"c1": {"field": "f.a", "op": "gt", "value": 50, "mode": "hard", "x": 1}},
            "rank": {"tie_break": "f.b", "tie_break_order": "asc"},
        },
        "dropped": (DroppedCriterion("c2", "f.z", "no such field", "not_in_catalogue"),),
        "notes": ("assumed 60 sessions",),
        "parts": (part,),
        "formulas": (
            DraftFormula("x", "f.a > 1 or f.b > 2", "bool", "", "", "", ("f.a",), None, "fp"),
        ),
        "missing": (MissingFeature(None, "slug", "span", "d", "w", (), "ok"),),
        "unresolved": (Unresolved("cheap", "cheap", 0, ()),),
    }
    return ScreenDraft(**(base | over))


# ------------------------------------------------------------------------------ prompt


def test_the_rubric_parse_is_strict_about_scores_and_issues() -> None:
    verdict = parse_verdict(FLAWED)
    assert verdict.scores["segmentation"] == 0 and not verdict.perfect
    assert verdict.issues[0] == Issue("segmentation", "connector-chip", "'but' is a chip")
    assert parse_verdict("```json\n" + PERFECT + "\n```").perfect
    bad = [
        "no json", "[]",
        json.dumps({"segmentation": 2, "coverage": 2, "logic": 2, "fidelity": 2}),
        json.dumps({"segmentation": 1, "coverage": 2, "logic": 2, "fidelity": 2, "issues": []}),
        json.dumps({"segmentation": 1, "coverage": 2, "logic": 2, "fidelity": 2, "issues": [
            {"dimension": "logic", "pattern": "x-y", "detail": "d"}]}),
        json.dumps({"segmentation": 2, "coverage": 2, "logic": 2, "fidelity": 2, "issues": [
            {"dimension": "logic", "pattern": "x-y", "detail": "d"}]}),
        json.dumps({"segmentation": 3, "coverage": 2, "logic": 2, "fidelity": 2}),
        json.dumps({"segmentation": True, "coverage": 2, "logic": 2, "fidelity": 2}),
        json.dumps({"segmentation": 2, "coverage": 2, "logic": 2, "fidelity": 2, "issues": 5}),
        json.dumps({"segmentation": 2, "coverage": 2, "logic": 2, "fidelity": 2, "issues": [1]}),
        *[
            json.dumps({"segmentation": 2, "coverage": 2, "logic": 2, "fidelity": 2,
                        "issues": [{"dimension": d, "pattern": p, "detail": t}]})
            for d, p, t in [
                ("x", "ok", "d"), ("logic", "Not Kebab", "d"),
                ("logic", "ok", "d" * 161)]
        ],
    ]  # fmt: skip
    for text in bad:
        with pytest.raises(InvalidAnswerError):
            parse_verdict(text)
    assert JUDGE_SCHEMA["required"][-1] == "issues"


def test_the_draft_is_rendered_compactly_with_every_element() -> None:
    text = render_draft(screen())
    for needle in (
        '"words":"iv rank above 50"', "criterion c1", '"op":"gt"', "tie_break f.b ascending",
        "formula x = f.a > 1 or f.b > 2", "missing slug", "unresolved 'cheap'", "dropped f.z",
        "note assumed 60 sessions",
    ):  # fmt: skip
        assert needle in text
    assert '"x"' not in text  # only field / op / value / mode of a criterion
    assert "parts: none" in render_draft(screen(parts=None, document={}))
    assert judge_user_prompt("s", screen()).startswith("SENTENCE: s\n\nDRAFT:\n")


# ------------------------------------------------------------------------------ one judgement


def judge_model(script: Sequence[str | Exception], costs: CostTap) -> Scripted:
    return Scripted(script, costs, model="judge")


class Checking(Scripted):
    """Applies ``accept`` as a chain does: the refused answer is repaired once."""

    def complete(  # type: ignore[override]
        self, system: str, user: str, *, tag: CallTag | None = None, schema: Any = None,
        accept: Any = None,
    ) -> Completion:  # fmt: skip
        self.tags = [*getattr(self, "tags", []), tag]
        for _ in range(2):
            got = super().complete(system, user, tag=tag, schema=schema)
            try:
                accept(got.text)
                return got
            except InvalidAnswerError:
                continue
        raise ModelUnavailableError("refused after one repair")


def test_an_invalid_verdict_is_repaired_once_else_counted_judge_invalid() -> None:
    costs = CostTap()
    fixed = Checking(["nonsense", PERFECT], costs)
    status, verdict, cost, asked = judge_once(fixed, "s", screen(), "me", costs)
    assert (status, verdict.perfect, cost, asked) == ("judged", True, 0.01, 2)  # type: ignore[union-attr]
    tag = fixed.tags[0]
    assert (tag.use_case, tag.user, tag.prompt_version) == ("golden-judge", "me", "1")
    assert judge_once(Checking(["nope"], costs), "s", screen(), None, costs)[0] == "judge_invalid"
    # a single adapter lets the refusal propagate; a model with no answer is unavailable
    assert (
        judge_once(judge_model(["nope"], costs), "s", screen(), None, costs)[0] == "judge_invalid"
    )
    down = judge_model([ModelUnavailableError("down")], costs)
    assert judge_once(down, "s", screen(), None, costs) == ("unavailable", None, None, 1)


# ------------------------------------------------------------------------------ aggregation


def test_means_perfect_share_and_patterns_aggregate_per_provider_and_case() -> None:
    rows = [
        Judged("p", "c1", "judged", parse_verdict(FLAWED), 0.1),
        Judged("p", "c2", "judged", parse_verdict(FLAWED)),
        Judged("p", "c2", "judged", parse_verdict(PERFECT)),
        Judged("p", "c2", "judge_invalid"),
        Judged("p", "c1", "unavailable"),
    ]
    m = measure(rows)
    assert (m["drafts"], m["judged"], m["judge_invalid"], m["unavailable"]) == (5, 3, 1, 1)
    assert m["means"]["segmentation"] == pytest.approx(2 / 3)
    assert m["perfect_share"] == pytest.approx(1 / 3) and m["cost_usd"] == 0.1
    top = top_patterns(rows)
    assert top[0] == {
        "pattern": "connector-chip", "dimension": "segmentation", "count": 2, "cases": ["c1", "c2"],
    }  # fmt: skip
    assert [t["pattern"] for t in top] == ["connector-chip", "or-as-and"]
    assert measure([])["means"]["logic"] is None and measure([])["perfect_share"] is None


def test_the_report_is_one_object_and_text_with_no_judge_free_text() -> None:
    plan = make_judge_plan(LLM, [case("c1")], ["paid"], "free", 1, 10)
    run = JudgeRun(
        [Judged("paid", "c1", "judged", parse_verdict(FLAWED))], {"paid": 2}, {"paid": 1},
        "--max-calls 10 reached",
    )  # fmt: skip
    rep = report(run, plan)
    assert rep["providers"]["paid"]["cases"]["c1"]["judged"] == 1
    assert "or became two" not in json.dumps(rep)
    text = "\n".join(report_lines(rep))
    assert "pattern connector-chip (segmentation) x1: c1" in text
    assert "1 of 2 drafts failed" in text and "STOPPED EARLY" in text


# ------------------------------------------------------------------------------ run and guards


def test_the_plan_counts_drafts_and_judge_calls_and_refuses_a_bad_one() -> None:
    plan = make_judge_plan(LLM, [case("a"), case("b")], ["paid", "free"], "free", 2, 100)
    assert plan.plan.calls == 8 and plan.calls == 16 and plan.estimate_usd > 0
    assert "8 drafts + 8 judge calls (free) = 16 calls (cap 100)" in plan.lines(100, 1.0)[0]
    with pytest.raises(ConfigurationError, match="over --max-calls"):
        make_judge_plan(LLM, [case("a")], ["paid"], "free", 3, 5)
    with pytest.raises(ConfigurationError, match="no judge provider"):
        make_judge_plan(LLM, [case("a")], ["paid"], "ghost", 1, 5)


def models(costs: CostTap, answers: Sequence[str | Exception]) -> Mapping[str, TextModel]:
    return {
        "paid": Scripted(['{"criteria": []}'], costs, model="drafter"),
        "free": judge_model(answers, costs),
    }


def test_a_run_drafts_then_judges_each_draft_and_stops_at_its_caps() -> None:
    costs = CostTap()
    plan = make_judge_plan(LLM, [case("c1"), case("c2")], ["paid"], "free", 1, 10)
    run = run_judge(plan, models(costs, [PERFECT]), draft, costs, "u", budget_usd=1.0, max_calls=10)
    assert [j.status for j in run.judged] == ["judged", "judged"] and run.stopped is None
    assert run.drafts == {"paid": 2} and run.drafts_failed == {"paid": 0}
    capped = run_judge(
        plan, models(CostTap(), [PERFECT]), draft, costs, None, budget_usd=1.0, max_calls=3
    )
    assert len(capped.judged) == 1 and capped.stopped == "--max-calls 3 reached"
    spent = CostTap()
    spent.submit({"cost_usd": 5.0})
    broke = run_judge(
        plan, models(spent, [PERFECT]), draft, spent, None, budget_usd=1.0, max_calls=10
    )
    assert not broke.judged and "--budget-usd" in (broke.stopped or "")


def test_a_provider_whose_judge_goes_down_is_left_and_the_next_still_runs() -> None:
    costs = CostTap()
    cases = [case(f"c{i}") for i in range(5)]
    plan = make_judge_plan(LLM, cases, ["paid", "free"], "free", 1, 40)
    plan = replace(plan, judge="j")
    down = [*[ModelUnavailableError("down")] * 3, PERFECT]
    both = {
        "paid": Scripted(['{"criteria": []}'], costs),
        "free": Scripted(['{"criteria": []}'], costs),
        "j": judge_model(down, costs),
    }
    run = run_judge(plan, both, draft, costs, None, budget_usd=1.0, max_calls=40)
    assert [j.status for j in run.judged].count("unavailable") == 3
    assert list(run.given_up) == ["paid"] and "3 times in a row" in run.given_up["paid"]
    assert run.stopped is None
    assert {j.provider for j in run.judged if j.status == "judged"} == {"free"}
    assert len([j for j in run.judged if j.provider == "free"]) == 5
    assert "GAVE UP ON paid" in "\n".join(report_lines(report(run, plan)))


def test_max_calls_counts_each_judge_request_a_repair_is_two() -> None:
    costs = CostTap()
    plan = make_judge_plan(LLM, [case("c1"), case("c2")], ["paid"], "free", 1, 10)
    both = {
        "paid": Scripted(['{"criteria": []}'], costs),
        "free": Checking(["nonsense", PERFECT], costs),
    }
    run = run_judge(plan, both, draft, costs, None, budget_usd=1.0, max_calls=4)
    assert len(run.judged) == 1 and run.stopped == "--max-calls 4 reached"  # 2 drafts + 2 requests


def test_a_draft_that_fails_is_counted_and_not_judged() -> None:
    costs = CostTap()
    plan = make_judge_plan(LLM, [case("c1")], ["paid"], "free", 1, 10)
    broken = {
        "paid": Scripted([ModelUnavailableError("down")], costs),
        "free": judge_model([PERFECT], costs),
    }
    run = run_judge(plan, broken, draft, costs, None, budget_usd=1.0, max_calls=10)
    assert run.judged == [] and run.drafts_failed == {"paid": 1}


class JudgeHarness(Harness):
    def open_models(self, ids: Sequence[str], costs: CostTap) -> Mapping[str, TextModel]:
        self.opened.append(tuple(ids))
        return {
            pid: Scripted([PERFECT if pid == "free" else '{"criteria": []}'], costs) for pid in ids
        }

    def judge(self, args: JudgeArgs, off: bool = False) -> int:
        return run_golden_judge(
            args, LLM, off, self.root, self.open_models, draft, self.out.append, self.notes.append
        )


def test_without_yes_it_spends_nothing_and_refuses_when_off_or_over_cap(tmp_path: Path) -> None:
    h = JudgeHarness(tmp_path)
    assert h.judge(JudgeArgs(providers=("paid",), judge="free")) == 1
    assert h.opened == [] and "nothing spent" in h.notes[-1] and "1 drafts + 1 judge" in h.notes[0]
    assert (
        h.judge(JudgeArgs(yes=True, judge="free"), off=True) == 1
        and "text model is off" in h.notes[-1]
    )
    assert h.judge(JudgeArgs(yes=True, judge="free", max_calls=1)) == 2 and h.opened == []
    assert h.judge(JudgeArgs(yes=True, judge="free", cases=("nope",))) == 2


def test_a_confirmed_run_opens_the_providers_and_the_judge_once_and_reports(tmp_path: Path) -> None:
    h = JudgeHarness(tmp_path)
    write_case(h.root, case("c2"))
    code = h.judge(JudgeArgs(yes=True, providers=("paid",), judge="free", as_json=True))
    assert code == 0 and h.opened == [("paid", "free")]
    rep = json.loads(h.out[0])
    assert rep["judge"] == "free" and rep["providers"]["paid"]["summary"]["perfect_share"] == 1.0
    h2 = JudgeHarness(tmp_path)
    assert h2.judge(JudgeArgs(yes=True, providers=("free",), judge="free")) == 0
    assert h2.opened == [("free",)] and "judge: free" in h2.out[0]


def test_it_refuses_before_any_draft_when_the_judge_may_not_answer_the_user(
    tmp_path: Path,
) -> None:
    class Barred(Scripted):
        def names_for(self, user: str | None) -> tuple[str, ...]:
            return ()

    class BarredHarness(JudgeHarness):
        def open_models(self, ids: Sequence[str], costs: CostTap) -> Mapping[str, TextModel]:
            self.opened.append(tuple(ids))
            return {pid: Barred(['{"criteria": []}'], costs) for pid in ids}

    h = BarredHarness(tmp_path)
    args = JudgeArgs(yes=True, providers=("paid",), judge="free", user="u")
    assert h.judge(args) == 2
    assert "may not answer user 'u'" in h.notes[-1] and h.out == []
