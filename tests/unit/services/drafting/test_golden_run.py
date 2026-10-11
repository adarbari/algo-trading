"""``algotrade-api golden run`` (``golden_run.py``): the live golden evaluation, driven here by
fake models (CI never calls the network): scoring and its aggregation, the consistency metric,
the guard rails (refusal, ``--yes``, the caps) and the ``--record`` file layout."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.llm import LlmSettings
from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ConfigurationError, ModelUnavailableError
from algotrade.services.drafting.golden import GoldenCase
from algotrade.services.drafting.golden_run import (
    UNAVAILABLE_STREAK,
    CostTap,
    Plan,
    RunArgs,
    RunResult,
    consistency,
    evaluate,
    make_plan,
    measure,
    percentile,
    recordings,
    report,
    report_lines,
    run_golden,
    select_cases,
    slug,
    write_recordings,
)
from algotrade.services.drafting.screens import ScreenDraft, criteria_of, parse_answer
from algotrade.services.text_model.model import TextModel

CATALOGUE = {"f.a", "f.b", "f.c"}
GOOD = json.dumps({"criteria": [{"field": "f.a", "op": "gt", "value": 10}]})
WRONG = json.dumps({"criteria": [{"field": "f.a", "op": "gt", "value": 99}]})
OTHER = json.dumps(
    {
        "criteria": [
            {"field": "f.a", "op": "gt", "value": 10},
            {"field": "f.b", "op": "gt", "value": 1},
        ]
    }
)
LLM = LlmSettings.from_document(
    {
        "enabled": True,
        "price": [
            {"model": "paid-model", "input_per_mtok": 1.0, "output_per_mtok": 5.0},
            {"model": "free-model", "free": True},
        ],
        "provider": [
            {
                "id": "paid",
                "base_url": "https://paid.example/v1",
                "model": "paid-model",
                "answer_limit": 1000,
            },
            {"id": "free", "base_url": "https://free.example/v1", "model": "free-model"},
        ],
    }
)


def case(case_id: str = "c1", split: str = "train") -> GoldenCase:
    part = {"span": "a", "bucket": "A", "fields": ["f.a"], "op": "gt", "value": 10, "tolerance": 0}
    return GoldenCase(case_id, f"sentence of {case_id}", split, (part,), frozenset())


class Scripted:
    """A model answering from a script (an ``Exception`` entry is raised), reporting its cost to
    the ``CostTap`` as the ledger would."""

    def __init__(
        self, script: Sequence[str | Exception], costs: CostTap, model: str = "m1"
    ) -> None:
        self.script, self.costs, self.model, self.n = list(script), costs, model, 0

    names = ("m",)

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self.names

    def complete(self, system: str, user: str, *, tag: CallTag | None = None) -> Completion:
        step = self.script[min(self.n, len(self.script) - 1)]
        self.n += 1
        if isinstance(step, Exception):
            raise step
        call_id = f"call-{id(self)}-{self.n}"
        self.costs.submit({"call_id": call_id, "cost_usd": 0.01})
        return Completion(
            step, self.model, "p", 100, 20, 2.0 * self.n, cache_read_tokens=50, call_id=call_id
        )


def draft(model: TextModel, sentence: str) -> ScreenDraft:
    answer = model.complete("system", sentence)
    kept, dropped = criteria_of(parse_answer(answer.text), CATALOGUE)
    return ScreenDraft("g", {"criteria": kept}, dropped, ())


def plan_of(
    cases: Sequence[GoldenCase], providers: Sequence[str] = ("paid",), repeat: int = 1
) -> Plan:
    return Plan(tuple(cases), tuple(providers), repeat, 0.0)


def run(
    script: Sequence[str | Exception],
    cases: Sequence[GoldenCase] = (),
    repeat: int = 3,
    **caps: Any,
) -> tuple[Plan, RunResult]:
    costs = CostTap()
    plan = plan_of(cases or [case()], repeat=repeat)
    result = evaluate(
        plan, {"paid": Scripted(script, costs)}, draft, costs,
        budget_usd=caps.get("budget_usd", 1.0), max_calls=caps.get("max_calls", 60),
    )  # fmt: skip
    return plan, result


# ------------------------------------------------------------------------------ the metrics


def test_percentiles_interpolate_and_empty_is_none() -> None:
    assert percentile([], 0.5) is None
    assert percentile([4.0], 0.9) == 4.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.9) == pytest.approx(4.6)


def test_consistency_is_the_mean_pairwise_jaccard_of_the_drafted_fields() -> None:
    same = frozenset({"f.a"})
    assert consistency([same, same, same]) == 1.0
    assert consistency([frozenset({"f.a"}), frozenset({"f.a", "f.b"})]) == 0.5
    assert consistency(
        [frozenset({"f.a"}), frozenset({"f.b"}), frozenset({"f.a"})]
    ) == pytest.approx(1 / 3)
    assert consistency([same]) is None and consistency([]) is None
    assert consistency([frozenset(), frozenset()]) == 1.0


def test_a_run_is_scored_and_measured_per_provider_and_case() -> None:
    plan, result = run([GOOD, WRONG, OTHER, "not json", ModelUnavailableError("down")], repeat=5)
    statuses = [(r.status, r.passed) for r in result.results]
    assert statuses == [
        ("ok", True), ("ok", False), ("ok", False), ("invalid", False), ("unavailable", False),
    ]  # fmt: skip
    m = measure(result.results)
    assert m["calls"] == 5 and m["pass_rate"] == 0.2
    assert m["invalid_rate"] == 0.2 and m["unavailable"] == 1
    assert m["consistency"] == pytest.approx((1 + 0.5 + 0.5) / 3)  # a vs b: {a} {a} {a,b}
    assert m["tokens_in"] == 100 and m["tokens_out"] == 20 and m["cache_read"] == 50
    assert m["cache_write"] is None  # never reported: unknown, not 0
    assert m["cost_usd"] == pytest.approx(0.04)
    assert m["latency_p50_s"] == pytest.approx(5.0)  # 2, 4, 6, 8 s: the answers that came
    rep = report(result, plan)
    assert rep["providers"]["paid"]["cases"]["c1"]["calls"] == 5
    assert rep["providers"]["paid"]["models"] == ["m1"]
    assert "summary" in "\n".join(report_lines(rep)) and "paid" in "\n".join(report_lines(rep))


def test_the_invalid_answer_keeps_its_raw_text_for_the_report() -> None:
    _, result = run(["not json"], repeat=1)
    bad = result.results[0]
    assert bad.status == "invalid" and bad.answer == "not json" and bad.model == "m1"


# ------------------------------------------------------------------------------ the caps


def test_a_run_stops_at_max_calls() -> None:
    _, result = run([GOOD], [case("c1"), case("c2")], repeat=3, max_calls=4)
    assert len(result.results) == 4 and "--max-calls 4" in (result.stopped or "")


def test_a_run_stops_when_the_spend_reaches_the_budget() -> None:
    _, result = run([GOOD], repeat=5, budget_usd=0.025)  # $0.01 a call: stops after the third
    assert len(result.results) == 3 and "--budget-usd" in (result.stopped or "")


def test_a_provider_that_is_down_is_given_up_on_but_the_next_still_runs() -> None:
    costs = CostTap()
    plan = plan_of([case()], ("paid", "free"), repeat=UNAVAILABLE_STREAK + 2)
    models = {
        "paid": Scripted([ModelUnavailableError("down")], costs),
        "free": Scripted([GOOD], costs),
    }
    result = evaluate(plan, models, draft, costs, budget_usd=1.0, max_calls=60)
    by = {p: [r.status for r in result.results if r.provider == p] for p in ("paid", "free")}
    assert by["paid"] == ["unavailable"] * UNAVAILABLE_STREAK
    assert by["free"] == ["ok"] * (UNAVAILABLE_STREAK + 2)
    assert "paid unavailable" in (result.stopped or "")


# ------------------------------------------------------------------------------ the plan


def test_the_plan_counts_calls_and_estimates_the_cheapest_cost() -> None:
    plan = make_plan(LLM, [case("a"), case("b")], ["paid", "free"], 3, 60)
    assert plan.calls == 12
    # paid: 12k input tokens at $1/M + 1000 answer tokens at $5/M = $0.017 a call; free: 0
    assert plan.estimate_usd == pytest.approx(0.017 * 6)


def test_a_plan_over_the_cap_an_unknown_provider_or_case_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="over --max-calls 5"):
        make_plan(LLM, [case()], ["paid", "free"], 3, 5)
    with pytest.raises(ConfigurationError, match="no provider"):
        make_plan(LLM, [case()], ["nope"], 1, 60)
    with pytest.raises(ConfigurationError, match="at least 1"):
        make_plan(LLM, [case()], ["paid"], 0, 60)
    cases = [case("a", "train"), case("b", "held_out")]
    assert [c.id for c in select_cases(cases, None, "held_out")] == ["b"]
    assert [c.id for c in select_cases(cases, ["a"], "all")] == ["a"]
    with pytest.raises(ConfigurationError, match="unknown case ids"):
        select_cases(cases, ["zzz"], "all")


# ------------------------------------------------------------------------------ the command


def write_case(root: Path, c: GoldenCase) -> None:
    (root / "cases").mkdir(parents=True, exist_ok=True)
    raw = {
        "id": c.id, "sentence": c.sentence, "split": c.split,
        "expect": {"parts": list(c.parts), "scope_fields": []},
    }  # fmt: skip
    (root / "cases" / f"{c.id}.json").write_text(json.dumps(raw))


class Harness:
    def __init__(self, tmp_path: Path, script: Sequence[str | Exception] = (GOOD,)) -> None:
        self.root, self.script = tmp_path / "golden", script
        write_case(self.root, case("c1"))
        self.out: list[str] = []
        self.notes: list[str] = []
        self.opened: list[tuple[str, ...]] = []

    def open_models(self, ids: Sequence[str], costs: CostTap) -> Mapping[str, TextModel]:
        self.opened.append(tuple(ids))
        return {pid: Scripted(self.script, costs, model="Model One") for pid in ids}

    def go(self, args: RunArgs, off: bool = False, settings: LlmSettings = LLM) -> int:
        return run_golden(
            args,
            settings,
            off,
            self.root,
            self.open_models,
            draft,
            self.out.append,
            self.notes.append,
        )


def test_it_refuses_while_the_text_model_is_off_and_says_how_to_enable_it(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    assert h.go(RunArgs(yes=True), off=True) == 1
    assert "unset ALGOTRADE_LLM" in h.notes[0] and "enabled = true" in h.notes[0]
    assert h.go(RunArgs(yes=True), settings=LlmSettings()) == 1  # not enabled in llm.toml
    assert h.opened == [] and h.out == []


def test_without_yes_it_prints_the_plan_and_spends_nothing(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    assert h.go(RunArgs(providers=("paid",), repeat=2)) == 1
    assert "1 cases x 1 providers (paid) x 2 repeats = 2 calls" in h.notes[0]
    assert "estimated cost" in h.notes[1] and "add --yes" in h.notes[-1]
    assert h.opened == [] and h.out == []


def test_a_plan_over_max_calls_is_refused_before_any_model_is_opened(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    assert h.go(RunArgs(repeat=3, max_calls=2, yes=True)) == 2
    assert "over --max-calls 2" in h.notes[0] and h.opened == []


def test_a_run_reports_json_and_by_default_asks_every_provider_of_the_file(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    assert h.go(RunArgs(repeat=2, as_json=True, yes=True)) == 0
    assert h.opened == [("paid", "free")]
    rep = json.loads(h.out[0])
    assert set(rep["providers"]) == {"paid", "free"}
    assert rep["providers"]["free"]["summary"]["pass_rate"] == 1.0


def test_record_writes_the_first_passing_raw_answer_per_model_and_case(tmp_path: Path) -> None:
    h = Harness(tmp_path, script=[WRONG, GOOD, GOOD])
    assert h.go(RunArgs(providers=("paid",), repeat=3, record=True, yes=True)) == 0
    path = h.root / "answers" / "model-one" / "c1.json"
    assert path.read_text().strip() == GOOD
    assert any(line == f"write: {path}" for line in h.notes)
    # replayable as the CI replay reads it
    kept, _ = criteria_of(parse_answer(path.read_text()), CATALOGUE)
    assert next(iter(kept.values()))["value"] == 10


def test_record_never_overwrites_without_force_and_skips_a_case_that_never_passed(
    tmp_path: Path,
) -> None:
    h = Harness(tmp_path, script=[GOOD])
    existing = h.root / "answers" / "model-one" / "c1.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("hand written")
    h.go(RunArgs(providers=("paid",), repeat=1, record=True, yes=True))
    assert existing.read_text() == "hand written"
    assert any(line.startswith("skip (exists, use --force)") for line in h.notes)
    h.go(RunArgs(providers=("paid",), repeat=1, record=True, force=True, yes=True))
    assert existing.read_text().strip() == GOOD
    failing = Harness(tmp_path / "x", script=[WRONG])
    failing.go(RunArgs(providers=("paid",), repeat=2, record=True, yes=True))
    assert not (failing.root / "answers").exists()


def test_slug_and_recordings_layout(tmp_path: Path) -> None:
    assert slug("Gemini 3 Flash/Preview") == "gemini-3-flash-preview"
    assert slug("///") == "model"
    written = write_recordings([(tmp_path / "a" / "b.json", "x")], force=False, say=lambda _: None)
    assert written == 1 and (tmp_path / "a" / "b.json").read_text() == "x\n"
    _, result = run([GOOD, WRONG], repeat=2)
    assert recordings(result, tmp_path) == [(tmp_path / "answers" / "m1" / "c1.json", GOOD)]
