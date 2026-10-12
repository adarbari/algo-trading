"""``algotrade-api golden run`` (``golden_run.py``): the live golden evaluation, driven here by
fake models (CI never calls the network): scoring and its aggregation, the consistency metric,
the guard rails (refusal, ``--yes``, the caps) and the ``--record`` file layout."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from algotrade.config.site.llm import LlmSettings
from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ConfigurationError, ModelUnavailableError
from algotrade.services.drafting.golden import GoldenCase
from algotrade.services.drafting.golden_run import (
    DEFAULT_RATE_WAIT_S,
    UNAVAILABLE_STREAK,
    CostTap,
    Plan,
    RunArgs,
    RunResult,
    consistency,
    drop_metrics,
    evaluate,
    make_plan,
    measure,
    percentile,
    recordings,
    repeats_of,
    report,
    report_lines,
    run_golden,
    select_cases,
    slug,
    write_recordings,
)
from algotrade.services.drafting.parts.model import PartsStats
from algotrade.services.drafting.screens import ScreenDraft, criteria_of, parse_answer
from algotrade.services.text_model.chain import FallbackTextModel
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

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: CallTag | None = None,
        schema: object = None,
        accept: object = None,
    ) -> Completion:
        step = self.script[min(self.n, len(self.script) - 1)]
        self.n += 1
        if isinstance(step, Exception):
            raise step
        call_id = f"call-{id(self)}-{self.n}"
        self.costs.submit({"call_id": call_id, "cost_usd": 0.01})
        return Completion(
            step, self.model, "p", 100, 20, 2.0 * self.n, cache_read_tokens=50, call_id=call_id
        )


def draft(model: TextModel, sentence: str, current: Mapping[str, Any] | None = None) -> ScreenDraft:
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


def test_a_chain_never_repairs_in_a_run_the_first_answer_is_scored_and_kept() -> None:
    costs = CostTap()
    inner = Scripted(["not json", GOOD], costs)
    chained = FallbackTextModel([("p", inner)])

    def with_accept(
        model: TextModel, sentence: str, current: Mapping[str, Any] | None = None
    ) -> ScreenDraft:
        def accept(text: str) -> None:
            parse_answer(text)

        answer = model.complete("system", sentence, accept=accept)
        kept, dropped = criteria_of(parse_answer(answer.text), CATALOGUE)
        return ScreenDraft("g", {"criteria": kept}, dropped, ())

    plan = plan_of([case()], repeat=1)
    result = evaluate(plan, {"paid": chained}, with_accept, costs, budget_usd=1.0, max_calls=5)
    bad = result.results[0]
    assert (bad.status, bad.answer) == ("invalid", "not json") and inner.n == 1


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


def test_a_curated_case_is_drafted_with_the_criteria_in_force_and_record_clears_its_flag(
    tmp_path: Path,
) -> None:
    force = {"criteria": {"c1": {"field": "f.b", "op": "gt", "value": 1}}}
    curated = GoldenCase("c1", "last paraphrase", "train", case().parts, frozenset(),
                         current=force, recorded=False)  # fmt: skip
    seen: list[Any] = []

    def spy(
        model: TextModel, sentence: str, current: Mapping[str, Any] | None = None
    ) -> ScreenDraft:
        seen.append((sentence, current))
        return draft(model, sentence)

    costs = CostTap()
    result = evaluate(plan_of([curated], repeat=1), {"paid": Scripted([GOOD], costs)}, spy, costs,
                      budget_usd=1.0, max_calls=5)  # fmt: skip
    assert seen == [("last paraphrase", force)]
    (tmp_path / "cases").mkdir()
    case_file = tmp_path / "cases" / "c1.json"
    case_file.write_text(json.dumps({"id": "c1", "recorded": False}))
    write_recordings(recordings(result, tmp_path), force=False, say=lambda _: None)
    assert "recorded" not in json.loads(case_file.read_text())


def test_suggestions_are_counted_per_call_and_never_change_the_score() -> None:
    answers = [json.dumps({"criteria": [], "suggestions": [1, 2]}), "not json"]

    def drafting(model: TextModel, sentence: str, current: Mapping[str, Any] | None = None) -> Any:
        text = model.complete("system", sentence).text
        offered = json.loads(text)["suggestions"]  # a bare list: only its length is reported
        made = draft(Scripted([GOOD], CostTap()), sentence)
        return replace(made, suggestions=tuple(offered))

    costs = CostTap()
    plan = plan_of([case()], repeat=1)
    result = evaluate(plan, {"paid": Scripted(answers[:1], costs)}, drafting, costs,
                      budget_usd=1.0, max_calls=5)  # fmt: skip
    (call,) = result.results
    assert call.suggestions == 2 and call.passed
    assert measure(result.results)["suggestions"] == 2


def test_the_explained_parts_measures_are_reported_apart_and_never_score_a_case() -> None:
    stats = PartsStats(
        items=4, by_model=3, by_fallback=1, spans=2, located=2, readings=2, readings_kept=1
    )

    def drafting(model: TextModel, sentence: str, current: Mapping[str, Any] | None = None) -> Any:
        return replace(draft(model, sentence), parts_stats=stats)

    costs = CostTap()
    result = evaluate(plan_of([case()], repeat=1), {"paid": Scripted([GOOD], costs)}, drafting,
                      costs, budget_usd=1.0, max_calls=5)  # fmt: skip
    (call,) = result.results
    assert call.passed and call.parts == stats
    assert measure(result.results)["parts"] == {
        "with_parts": 1, "model_share": 0.75, "located_share": 1.0, "not_understood": 0,
        "readings_kept": 0.5,
    }  # fmt: skip
    plain = evaluate(plan_of([case()], repeat=1), {"paid": Scripted([GOOD], CostTap())}, draft,
                     costs, budget_usd=1.0, max_calls=5)  # fmt: skip
    assert measure(plain.results)["parts"]["with_parts"] == 0
    rep = report(result, plan_of([case()], repeat=1))
    assert any("parts: 1 drafts, model placed 75%" in line for line in report_lines(rep))


# ------------------------------------------------------------------------ drops, pacing, 429

LIMITED = ModelUnavailableError("HTTP 429: slow down")
SENTENCE_WHY = "my own sentence about low value stocks"


def waits_run(
    script: Sequence[str | Exception], *, repeat: int = 1, **kw: Any
) -> tuple[RunResult, list[tuple[str, float]]]:
    costs, waits = CostTap(), []
    result = evaluate(
        plan_of([case()], repeat=repeat), {"paid": Scripted(script, costs)}, draft, costs,
        budget_usd=kw.pop("budget_usd", 1.0), max_calls=kw.pop("max_calls", 60),
        sleep=lambda provider, seconds: waits.append((provider, seconds)), **kw,
    )  # fmt: skip
    return result, waits


def test_a_429_waits_and_retries_the_same_call_twice_then_is_unavailable() -> None:
    result, waits = waits_run([LIMITED], batch_pause_s=7.0)
    (only,) = result.results
    assert (only.status, only.rate_limit_retries) == ("unavailable", 2)
    assert waits == [("paid", 7.0), ("paid", 7.0)]


def test_a_429_that_clears_is_scored_and_the_wait_defaults_without_a_batch_pause() -> None:
    result, waits = waits_run([LIMITED, GOOD])
    (only,) = result.results
    assert (only.status, only.rate_limit_retries) == ("ok", 1)
    assert waits == [("paid", DEFAULT_RATE_WAIT_S)]


def test_retries_count_as_calls_and_never_pass_max_calls() -> None:
    costs = CostTap()
    model = Scripted([LIMITED], costs)
    result = evaluate(
        plan_of([case()], repeat=3), {"paid": model}, draft, costs, budget_usd=1.0, max_calls=2
    )
    assert model.n == 2 and "--max-calls 2" in (result.stopped or "")
    assert result.results[0].rate_limit_retries == 1  # the second try was the last allowed


def test_only_a_429_is_retried() -> None:
    result, waits = waits_run([ModelUnavailableError("HTTP 500")])
    assert result.results[0].rate_limit_retries == 0 and waits == []


def test_pace_waits_between_calls_not_before_the_first() -> None:
    _, waits = waits_run([GOOD], repeat=3, pace_s=2.0)
    assert waits == [("paid", 2.0)] * 2


def test_a_batch_pause_comes_after_every_n_calls_counting_from_the_last_pause() -> None:
    _, waits = waits_run([GOOD], repeat=7, batch=3, batch_pause_s=9.0)
    assert waits == [("paid", 9.0)] * 2  # before the 4th and the 7th call
    # a 429 wait is a pause: the batch count restarts after it
    _, waits = waits_run([GOOD, LIMITED, GOOD, GOOD, GOOD, GOOD], repeat=5, batch=3,
                         batch_pause_s=9.0)  # fmt: skip
    assert [w for _, w in waits] == [9.0, 9.0]  # the 429 wait, then one batch pause


def kinds_of(answer: dict[str, Any]) -> list[tuple[str, str]]:
    _, dropped = criteria_of(answer, CATALOGUE)
    return [(d.kind, d.field) for d in dropped]


def test_drop_kinds_come_from_the_check_not_from_the_reason_text() -> None:
    answer = {
        "criteria": [
            {"field": "iv30", "op": "gt", "value": 1},
            {"field": "f.a", "op": "huh", "value": 1},
            {"field": "f.a", "op": "gt", "value": [1], "why": "low value"},
            {"field": "f.a", "op": "gt", "value": 1, "mode": "odd", "why": "low value"},
        ]
    }
    assert kinds_of(answer) == [
        ("not_in_catalogue", "iv30"),
        ("bad_op", "f.a"),
        ("bad_value", "f.a"),
        ("bad_mode", "f.a"),  # not bad_value, though its why says "value"
    ]


def private_run() -> RunResult:
    bad = json.dumps(
        {
            "criteria": [
                {"field": "iv30", "op": "gt", "value": 1, "why": SENTENCE_WHY},
                {"field": "f.a", "op": "gt", "value": [1], "why": SENTENCE_WHY},
            ]
        }
    )
    return run([bad, "not json", GOOD], repeat=3)[1]


def test_drop_metrics_count_kinds_invented_fields_and_would_repair() -> None:
    m = drop_metrics(private_run().results)
    assert m["drops_total"] == 2
    assert m["drops_by_kind"] == {"not_in_catalogue": 1, "bad_value": 1}
    assert m["invented_field_drops"] == {"count": 1, "top": {"iv30": 1}}
    assert m["would_repair"] == 1 and "repaired" not in m


def test_repeats_of_lists_each_drop_without_the_models_free_text() -> None:
    first, second, third = repeats_of(private_run().results)
    assert [d["kind"] for d in first["dropped"]] == ["not_in_catalogue", "bad_value"]
    assert (second["status"], third["dropped"]) == ("invalid", [])
    assert SENTENCE_WHY not in json.dumps(repeats_of(private_run().results))


def test_json_output_never_carries_the_models_why(tmp_path: Path) -> None:
    bad = json.dumps({"criteria": [{"field": "iv30", "op": "gt", "value": 1, "why": SENTENCE_WHY}]})
    h = Harness(tmp_path, [bad])
    assert h.go(RunArgs(("c1",), "all", (), 1, False, False, True, 60, 1.0, True)) == 0
    assert SENTENCE_WHY not in "".join(h.out) and "not_in_catalogue" in "".join(h.out)


def test_the_builder_reason_keeps_the_why_while_detail_does_not() -> None:
    _, (d,) = criteria_of(
        {"criteria": [{"field": "iv30", "op": "gt", "value": 1, "why": SENTENCE_WHY}]}, CATALOGUE
    )
    assert d.reason.endswith(f"({SENTENCE_WHY})") and SENTENCE_WHY not in d.detail


def test_json_never_carries_a_text_value_or_a_non_string_why(tmp_path: Path) -> None:
    secret = "buy cheap tech names my own words"
    bad = json.dumps(
        {
            "criteria": [
                {"field": "f.a", "op": "gt", "value": secret, "tolerance": secret, "why": 5},
                {"field": "f.b", "op": "gt", "value": [secret], "why": {"x": secret}},
                {"field": "f.a", "op": "between", "value": [secret], "mode": secret},
            ]
        }
    )
    h = Harness(tmp_path, [bad])
    assert h.go(RunArgs(("c1",), "all", (), 1, False, False, True, 60, 1.0, True)) == 0
    out = "".join(h.out)
    assert secret not in out and "criteria[" in out


def test_a_draft_made_without_the_model_is_scored_and_costs_nothing() -> None:
    """A draft the phrasebook made (``stage``, not the absence of a completion, says so) is still
    scored, with no tokens and a zero cost, never silently failed."""
    costs = CostTap()
    scripted = Scripted([GOOD], costs)

    def phrasebook_draft(model: TextModel, sentence: str, current: Any = None) -> ScreenDraft:
        kept, _ = criteria_of(parse_answer(GOOD), CATALOGUE)
        return ScreenDraft("g", {"criteria": kept}, (), (), stage="phrasebook")

    result = evaluate(plan_of([case()]), {"paid": scripted}, phrasebook_draft, costs,
                      budget_usd=1.0, max_calls=60)  # fmt: skip
    (one,) = result.results
    assert scripted.n == 0
    assert (one.status, one.passed, one.model, one.cost_usd) == ("ok", True, "phrasebook", 0.0)
    assert one.input_tokens is None and one.fields == {"f.a"}
