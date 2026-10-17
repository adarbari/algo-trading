"""``algotrade-api golden judge``: the owner-run LLM judge over the golden set (ADR 0041, amended
2026-10-17). The structural score of ``golden run`` cannot see bad segmentation or wrong connector
logic, so a judge model reads each real draft against its sentence and scores it 0-2 on
segmentation, coverage, logic and fidelity (the rubric is ``judge_prompt.py``).

    algotrade-api golden judge [--cases ID,...] [--split train|held_out|all] [--provider ID ...]
        [--judge ID=claude] [--repeat N=1] [--json] [--max-calls N=60] [--budget-usd X=1.00]
        [--user ID] --yes

For each case and drafting provider it runs the real ``draft_screen`` ``--repeat`` times (the
machinery of ``golden_run``: same drafter, ``evaluate``, plan and caps), then asks ``--judge`` (one
provider of ``llm.toml``, use case ``golden-judge``) to score each draft. An invalid verdict is
repaired once through the chain's ``accept`` check, else counted as ``judge_invalid``. Per drafting
provider it reports the mean of each dimension, the share of perfect drafts and the top patterns
with counts and case ids; ``--json`` prints the same as one object.

Guard rails as ``golden run``: refused while the text model is off; the plan (drafts, judge calls,
estimated cost) is printed first and nothing is spent without ``--yes``; a plan over ``--max-calls``
is refused, a run stops at ``--budget-usd`` and after three unavailable answers in a row. Owner-run
only: CI never calls a model and the request path never judges."""

import json
import statistics
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from algotrade.config.site.llm import LlmSettings
from algotrade.core.model.completion import CallTag
from algotrade.core.model.errors import (
    ConfigurationError,
    InvalidAnswerError,
    ModelUnavailableError,
)
from algotrade.services.drafting.golden.golden import GoldenCase, load_cases
from algotrade.services.drafting.golden.golden_run import (
    UNAVAILABLE_STREAK,
    CallResult,
    CostTap,
    Draft,
    Plan,
    call_estimate_usd,
    evaluate,
    make_plan,
    select_cases,
)
from algotrade.services.drafting.golden.judge_prompt import (
    DIMENSIONS,
    JUDGE_PROMPT_VERSION,
    JUDGE_SCHEMA,
    JUDGE_SYSTEM,
    Issue,
    Verdict,
    judge_user_prompt,
    parse_verdict,
)
from algotrade.services.drafting.screens import ScreenDraft
from algotrade.services.text_model.model import TextModel

USE_CASE = "golden-judge"
DEFAULT_JUDGE = "claude"
DEFAULT_REPEAT, DEFAULT_MAX_CALLS, DEFAULT_BUDGET_USD = 1, 60, 1.00
TOP_PATTERNS = 10


@dataclass(frozen=True)
class Judged:
    """One draft's outcome: ``status`` ``judged`` (a ``verdict``), ``judge_invalid`` (the judge
    answered, the verdict stayed unusable after one repair) or ``unavailable`` (no answer)."""

    provider: str
    case: str
    status: str
    verdict: Verdict | None = None
    cost_usd: float | None = None


@dataclass
class JudgeRun:
    judged: list[Judged] = field(default_factory=list)
    drafts: dict[str, int] = field(default_factory=dict)  # provider -> drafts asked
    drafts_failed: dict[str, int] = field(default_factory=dict)  # provider -> no usable draft
    stopped: str | None = None  # a cap that ended the whole run
    given_up: dict[str, str] = field(default_factory=dict)  # provider -> why it was left


def judge_once(
    model: TextModel, sentence: str, draft: ScreenDraft, user: str | None, costs: CostTap
) -> tuple[str, Verdict | None, float | None, int]:
    """Ask the judge once for ``draft``: (status, verdict, cost, requests). ``requests`` counts
    the model requests made (each answer ``accept`` checked; a repair makes it 2, at least 1).
    The answer is checked by ``parse_verdict`` as the chain's ``accept`` (one repair); a refusal
    that no repair cured is ``judge_invalid``, any other failure ``unavailable``."""
    refused: list[bool] = []
    asked: list[bool] = []

    def accept(text: str) -> None:
        asked.append(True)
        try:
            parse_verdict(text)
        except InvalidAnswerError:
            refused.append(True)
            raise

    tag = CallTag(USE_CASE, user, JUDGE_PROMPT_VERSION)
    try:
        got = model.complete(
            JUDGE_SYSTEM, judge_user_prompt(sentence, draft), tag=tag, schema=JUDGE_SCHEMA,
            accept=accept,
        )  # fmt: skip
        return "judged", parse_verdict(got.text), costs.cost_of(got.call_id), max(1, len(asked))
    except InvalidAnswerError:  # a single adapter lets the refusal propagate
        return "judge_invalid", None, None, max(1, len(asked))
    except ModelUnavailableError as exc:
        cost = costs.cost_of(getattr(exc, "call_id", None))
        status = "judge_invalid" if refused else "unavailable"
        return status, None, cost, max(1, len(asked))


def capturing(draft: Draft, made: list[ScreenDraft]) -> Draft:
    """``draft`` that keeps each draft it makes in ``made`` (``evaluate`` scores and drops them)."""

    def capture(model: TextModel, sentence: str, current: Mapping[str, Any] | None) -> ScreenDraft:
        made.append(draft(model, sentence, current))
        return made[-1]

    return capture


# ------------------------------------------------------------------------------ the plan


@dataclass(frozen=True)
class JudgePlan:
    """The drafting ``plan``, the ``judge`` provider and the whole estimate (drafts + judge)."""

    plan: Plan
    judge: str
    estimate_usd: float

    @property
    def calls(self) -> int:
        return self.plan.calls * 2  # a draft, then its verdict

    def lines(self, max_calls: int, budget_usd: float) -> list[str]:
        p = self.plan
        return [
            f"plan: {len(p.cases)} cases x {len(p.providers)} providers "
            f"({', '.join(p.providers)}) x {p.repeat} repeats = {p.calls} drafts + "
            f"{p.calls} judge calls ({self.judge}) = {self.calls} calls (cap {max_calls})",
            f"estimated cost ~${self.estimate_usd:.3f} (cap ${budget_usd:.2f})",
        ]


def make_judge_plan(
    settings: LlmSettings,
    cases: Sequence[GoldenCase],
    providers: Sequence[str],
    judge: str,
    repeat: int,
    max_calls: int,
) -> JudgePlan:
    """The plan; ``ConfigurationError`` for an unknown provider or judge, a bad ``repeat`` or a
    plan over ``max_calls`` (drafts and judge calls together)."""
    by_id = {p.id: p for p in settings.providers}
    if judge not in by_id:
        raise ConfigurationError(
            f"llm.toml has no judge provider {judge!r}: it has {sorted(by_id)}"
        )
    drafts = make_plan(settings, cases, providers, repeat, max_calls * 2)
    plan = JudgePlan(
        drafts,
        judge,
        drafts.estimate_usd + drafts.calls * call_estimate_usd(settings, by_id[judge]),
    )
    if plan.calls > max_calls:
        raise ConfigurationError(
            f"the plan is {plan.calls} calls (drafts and judge), over --max-calls {max_calls}: "
            "narrow --cases / --provider / --repeat or raise the cap"
        )
    return plan


# ------------------------------------------------------------------------------ one run


def run_judge(
    plan: JudgePlan,
    models: Mapping[str, TextModel],
    draft: Draft,
    costs: CostTap,
    user: str | None,
    *,
    budget_usd: float,
    max_calls: int,
) -> JudgeRun:
    """Draft each provider's cases through ``golden_run.evaluate`` (capturing the drafts), then
    judge each draft. Stops (reason in ``stopped``) at ``max_calls`` (drafts and judge calls) or
    ``budget_usd`` and after ``UNAVAILABLE_STREAK`` unavailable judge answers in a row."""
    run, calls = JudgeRun(), 0
    by_case = {c.id: c for c in plan.plan.cases}
    judge = models[plan.judge]
    for provider in plan.plan.providers:
        made: list[ScreenDraft] = []
        streak = 0
        one = Plan(plan.plan.cases, (provider,), plan.plan.repeat, 0.0)
        drafted = evaluate(
            one, {provider: models[provider]}, capturing(draft, made), costs, budget_usd=budget_usd,
            max_calls=max_calls - calls,
        )  # fmt: skip
        results = drafted.results
        calls += sum(1 + r.rate_limit_retries for r in results)
        usable: list[tuple[CallResult, ScreenDraft]] = list(
            zip([r for r in results if r.status == "ok"], made, strict=True)
        )
        run.drafts[provider] = len(results)
        run.drafts_failed[provider] = len(results) - len(usable)
        if drafted.stopped:
            if _ends_run(drafted.stopped):
                run.stopped = drafted.stopped
            else:
                run.given_up[provider] = drafted.stopped
        for result, made_draft in usable:
            stop = _stop_reason(calls, max_calls, costs, budget_usd)
            if stop:
                run.stopped = stop
                return run
            if streak >= UNAVAILABLE_STREAK:
                run.given_up[provider] = (
                    f"the judge was unavailable {UNAVAILABLE_STREAK} times in a row"
                )
                break
            status, verdict, cost, requests = judge_once(
                judge, by_case[result.case].sentence, made_draft, user, costs
            )
            calls += requests
            streak = streak + 1 if status == "unavailable" else 0
            run.judged.append(Judged(provider, result.case, status, verdict, cost))
        if run.stopped:
            return run
    return run


def _ends_run(reason: str) -> bool:
    """A cap (``--max-calls`` / ``--budget-usd``) ends the whole run; a provider that stopped
    answering only ends its own drafts."""
    return reason.startswith("--")


def _stop_reason(calls: int, max_calls: int, costs: CostTap, budget: float) -> str | None:
    if calls >= max_calls:
        return f"--max-calls {max_calls} reached"
    if costs.spent >= budget:
        return f"--budget-usd {budget:.2f} reached (${costs.spent:.3f})"
    return None


# ------------------------------------------------------------------------------ the report


def _scored(rows: Sequence[Judged]) -> list[Verdict]:
    return [r.verdict for r in rows if r.verdict is not None]


def measure(rows: Sequence[Judged]) -> dict[str, Any]:
    """The metrics of a group of judged drafts: counts, the mean of each dimension, the share of
    perfect drafts (of those judged) and the cost."""
    verdicts = _scored(rows)
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    return {
        "drafts": len(rows),
        "judged": len(verdicts),
        "judge_invalid": sum(r.status == "judge_invalid" for r in rows),
        "unavailable": sum(r.status == "unavailable" for r in rows),
        "means": {
            d: statistics.fmean(v.scores[d] for v in verdicts) if verdicts else None
            for d in DIMENSIONS
        },
        "perfect_share": sum(v.perfect for v in verdicts) / len(verdicts) if verdicts else None,
        "cost_usd": sum(costs) if costs else None,
    }


def top_patterns(rows: Sequence[Judged], limit: int = TOP_PATTERNS) -> list[dict[str, Any]]:
    """The most frequent issue patterns: ``pattern``, ``dimension`` (the most named), ``count``
    and the sorted ``cases`` that showed it. Never the judge's free-text detail."""
    counts: dict[str, int] = defaultdict(int)
    cases: dict[str, set[str]] = defaultdict(set)
    dims: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        issues: Sequence[Issue] = row.verdict.issues if row.verdict else ()
        for issue in issues:
            counts[issue.pattern] += 1
            cases[issue.pattern].add(row.case)
            dims[issue.pattern][issue.dimension] += 1
    ordered = sorted(counts, key=lambda p: (-counts[p], p))[:limit]
    return [
        {"pattern": p, "dimension": max(dims[p], key=lambda d: dims[p][d]), "count": counts[p],
         "cases": sorted(cases[p])}
        for p in ordered
    ]  # fmt: skip


def report(run: JudgeRun, plan: JudgePlan) -> dict[str, Any]:
    """Everything the run measured, by drafting provider, then case (``--json`` prints this)."""
    out: dict[str, Any] = {
        "stopped": run.stopped, "given_up": run.given_up, "judge": plan.judge,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "planned_calls": plan.calls, "providers": {},
    }  # fmt: skip
    for provider in plan.plan.providers:
        mine = [r for r in run.judged if r.provider == provider]
        out["providers"][provider] = {
            "drafts_asked": run.drafts.get(provider, 0),
            "drafts_failed": run.drafts_failed.get(provider, 0),
            "summary": measure(mine),
            "patterns": top_patterns(mine),
            "cases": {
                c.id: measure([r for r in mine if r.case == c.id])
                for c in plan.plan.cases
                if any(r.case == c.id for r in mine)
            },
        }
    return out


def _fmt(value: float | None, spec: str) -> str:
    return "-" if value is None else format(value, spec)


def _row(label: str, m: Mapping[str, Any]) -> str:
    means = " ".join(f"{_fmt(m['means'][d], '.2f'):>6}" for d in DIMENSIONS)
    return (
        f"{label:<34} {m['judged']:>3}/{m['drafts']:<3} {means} "
        f"{_fmt(m['perfect_share'], '.0%'):>7} {m['judge_invalid']:>7}"
    )


def report_lines(rep: Mapping[str, Any]) -> list[str]:
    """The report as text: per drafting provider its cases, total and top patterns."""
    header = (
        f"{'provider / case':<34} {'judged':>7} "
        + " ".join(f"{d[:6]:>6}" for d in DIMENSIONS)
        + f" {'perfect':>7} {'invalid':>7}"
    )
    lines: list[str] = [f"judge: {rep['judge']} (prompt v{rep['judge_prompt_version']})"]
    for provider, data in rep["providers"].items():
        lines += [
            "",
            f"{provider}: {data['drafts_failed']} of {data['drafts_asked']} drafts failed",
            header,
        ]
        lines += [_row(f"  {cid}", m) for cid, m in data["cases"].items()]
        lines.append(_row("  TOTAL", data["summary"]))
        for pat in data["patterns"]:
            lines.append(
                f"  pattern {pat['pattern']} ({pat['dimension']}) x{pat['count']}: "
                + ", ".join(pat["cases"])
            )
    lines += [f"GAVE UP ON {p}: {why}" for p, why in rep["given_up"].items()]
    if rep["stopped"]:
        lines.append(f"STOPPED EARLY: {rep['stopped']}")
    return lines


# ------------------------------------------------------------------------------ the command


@dataclass(frozen=True)
class JudgeArgs:
    cases: tuple[str, ...] = ()
    split: str = "all"
    providers: tuple[str, ...] = ()
    judge: str = DEFAULT_JUDGE
    repeat: int = DEFAULT_REPEAT
    as_json: bool = False
    max_calls: int = DEFAULT_MAX_CALLS
    budget_usd: float = DEFAULT_BUDGET_USD
    yes: bool = False
    user: str | None = None


def run_golden_judge(
    args: JudgeArgs,
    settings: LlmSettings,
    switch_off: bool,
    root: Path,
    open_models: Callable[[Sequence[str], CostTap], Mapping[str, TextModel]],
    draft: Draft,
    say: Callable[[str], None],
    note: Callable[[str], None],
) -> int:
    """The command: refuse, plan, require ``--yes``, draft and judge, report. ``say`` gets the
    report, ``note`` everything else. -> the exit code (0 done, 1 refused or not confirmed, 2 a
    bad argument)."""
    if switch_off or not settings.enabled:
        note(
            "refused: the text model is off. Enable it: unset ALGOTRADE_LLM (it is `off`) and "
            "set `enabled = true` in config/site/llm.toml (or your llm.local.toml)."
        )
        return 1
    try:
        cases = select_cases(load_cases(root), args.cases or None, args.split)
        providers = args.providers or tuple(p.id for p in settings.providers)
        plan = make_judge_plan(settings, cases, providers, args.judge, args.repeat, args.max_calls)
    except ConfigurationError as exc:
        note(f"refused: {exc}")
        return 2
    for line in plan.lines(args.max_calls, args.budget_usd):
        note(line)
    if not args.yes:
        note("nothing spent: add --yes to run it.")
        return 1
    costs = CostTap()
    try:
        models = open_models(tuple(dict.fromkeys((*providers, args.judge))), costs)
    except ConfigurationError as exc:
        note(f"refused: {exc}")
        return 2
    if not models[args.judge].names_for(args.user):
        note(
            f"refused: judge {args.judge!r} may not answer user {args.user!r} "
            "(llm.toml only_users, or no user: pass --user)"
        )
        return 2
    run = run_judge(
        plan, models, draft, costs, args.user, budget_usd=args.budget_usd,
        max_calls=args.max_calls,
    )  # fmt: skip
    rep = report(run, plan)
    say(json.dumps(rep, indent=2) if args.as_json else "\n".join(report_lines(rep)))
    return 0
