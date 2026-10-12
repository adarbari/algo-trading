"""``algotrade-api golden run``: the owner-run LIVE evaluation of the drafting prompt against the
golden set (docs/drafting/describe-it-plan.md, "Reliability" and "Learning from iteration").
The replay in CI only parses recorded answers; this asks real models and measures them. CI never
runs it (no network): tests drive it with fake models.

    algotrade-api golden run [--cases ID,...] [--split train|held_out|all] [--provider ID ...]
        [--repeat N=3] [--record [--force]] [--json] [--max-calls 60] [--budget-usd 1.00]
        [--user ID] --yes

For each case of ``tests/fixtures/drafting/golden`` and each provider (the chain of the machine's
``llm.toml`` restricted to that one provider; default: every provider of the file), it runs the
real ``draft_screen`` ``--repeat`` times as ``--user`` (default ``$ALGOTRADE_USER``; the owner,
whose login a ``claude-cli`` provider answers) and scores each draft structurally
(``services/drafting/golden.py``). Per provider and case, and per provider overall, it reports:
pass rate, field agreement across the repeats (mean pairwise Jaccard of the sets of fields
drafted; ``-`` below two answered repeats), invalid-answer rate (the model answered, the draft
could not be parsed or validated), unavailable count (no answer), mean tokens in / out / cache
read / cache write, latency p50 / p90 and cost (from the usage ledger's rows of the call; the
rows are written to ``usage/llm_calls`` as usual). ``--json`` prints the same as one object.

Guard rails: refused while ``$ALGOTRADE_LLM=off`` or ``llm.toml`` is not enabled (the message
says how to turn it on); the plan (calls, estimated cost) is printed first and nothing is spent
without ``--yes``; a plan over ``--max-calls`` is refused, a run stops at ``--budget-usd``
(spend as the ledger counted it) and after three unavailable answers in a row from a provider;
the usage ledger's own ``[budget]`` applies as always (a refused call is "unavailable"). No key
is ever printed.

``--record`` writes the raw text of the first passing answer of each case to
``tests/fixtures/drafting/golden/answers/<model-slug>/<case-id>.json`` for the CI replay: it
prints the files first, never overwrites an existing one (hand-written seeds included) without
``--force`` and writes nothing for a case that never passed."""

import json
import re
import statistics
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

from algotrade.config.site.llm import LlmSettings, ProviderSettings, Rate
from algotrade.core.model.completion import CallTag, Completion
from algotrade.core.model.errors import ConfigurationError, ModelUnavailableError
from algotrade.services.drafting.golden import GoldenCase, load_cases, mark_recorded, score
from algotrade.services.drafting.screens import ScreenDraft, draft_screen
from algotrade.services.read.context import ReadContext
from algotrade.services.text_model.model import TextModel

SCREENER_ID = "golden-eval"
GOLDEN_ROOT = Path("tests") / "fixtures" / "drafting" / "golden"
DEFAULT_REPEAT, DEFAULT_MAX_CALLS, DEFAULT_BUDGET_USD = 3, 60, 1.00
ESTIMATE_INPUT_TOKENS = 12_000  # the retrieval-slice target of the plan: what a call is priced at
UNAVAILABLE_STREAK = 3  # unavailable answers in a row after which a provider is given up on
SPLITS = ("train", "held_out", "all")

type Draft = Callable[[TextModel, str, Mapping[str, Any] | None], ScreenDraft]


def drafter(ctx: ReadContext) -> Draft:
    """The real ``draft_screen`` over ``ctx`` (the caller's catalogue), as ``evaluate`` calls it."""
    return lambda model, sentence, current: draft_screen(ctx, model, SCREENER_ID, sentence, current)


# ------------------------------------------------------------------------------ the plan


@dataclass(frozen=True)
class Plan:
    """What a run would do: the ``cases``, the ``providers``, ``repeat`` and what that costs."""

    cases: tuple[GoldenCase, ...]
    providers: tuple[str, ...]
    repeat: int
    estimate_usd: float

    @property
    def calls(self) -> int:
        return len(self.cases) * len(self.providers) * self.repeat

    def lines(self, max_calls: int, budget_usd: float) -> list[str]:
        return [
            f"plan: {len(self.cases)} cases x {len(self.providers)} providers "
            f"({', '.join(self.providers)}) x {self.repeat} repeats = {self.calls} calls "
            f"(cap {max_calls})",
            f"estimated cost ~${self.estimate_usd:.3f} "
            f"(at {ESTIMATE_INPUT_TOKENS} input tokens a call; cap ${budget_usd:.2f})",
        ]


def select_cases(
    cases: Sequence[GoldenCase], ids: Sequence[str] | None, split: str
) -> tuple[GoldenCase, ...]:
    """The cases of ``split`` (``all``: both), narrowed to ``ids`` (an unknown id is an error)."""
    if split not in SPLITS:
        raise ConfigurationError(f"--split must be one of {SPLITS}")
    if ids:
        unknown = sorted(set(ids) - {c.id for c in cases})
        if unknown:
            raise ConfigurationError(f"unknown case ids: {unknown}")
    chosen = tuple(c for c in cases if (split in ("all", c.split)) and (not ids or c.id in ids))
    if not chosen:
        raise ConfigurationError("no golden case matches --cases / --split")
    return chosen


def call_estimate_usd(settings: LlmSettings, provider: ProviderSettings) -> float:
    """What one call to ``provider`` costs at ``ESTIMATE_INPUT_TOKENS`` (a login: the budget's
    ``reported_call_usd``; a free provider 0)."""
    rate: Rate = settings.rate(provider)
    if not rate.spends:
        return 0.0
    if rate.input_per_mtok == 0.0 and rate.output_per_mtok == 0.0:  # a reported (login) rate
        return settings.budget.reported_call_usd
    return (
        ESTIMATE_INPUT_TOKENS * rate.input_per_mtok + rate.answer_limit * rate.output_per_mtok
    ) / 1e6


def make_plan(
    settings: LlmSettings,
    cases: Sequence[GoldenCase],
    providers: Sequence[str],
    repeat: int,
    max_calls: int,
) -> Plan:
    """The plan for ``providers`` (ids of ``settings``); ``ConfigurationError`` for an unknown
    provider, a ``repeat`` below 1 or a plan over ``max_calls``."""
    if repeat < 1:
        raise ConfigurationError("--repeat must be at least 1")
    by_id = {p.id: p for p in settings.providers}
    unknown = sorted(set(providers) - set(by_id))
    if unknown:
        raise ConfigurationError(f"llm.toml has no provider {unknown}: it has {sorted(by_id)}")
    per_call = sum(call_estimate_usd(settings, by_id[p]) for p in providers)
    plan = Plan(tuple(cases), tuple(providers), repeat, per_call * len(cases) * repeat)
    if plan.calls > max_calls:
        raise ConfigurationError(
            f"the plan is {plan.calls} calls, over --max-calls {max_calls}: "
            "narrow --cases / --provider / --repeat or raise the cap"
        )
    return plan


# ------------------------------------------------------------------------------ one run


class CostTap:
    """Collects the usage rows the ledger records (``open_text_model(tee=tap.submit)``): the
    cost of a call is the sum of the rows with its ``call_id``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_call: dict[str, float] = {}
        self._total = 0.0

    def submit(self, row: Mapping[str, Any]) -> None:
        cost = row.get("cost_usd")
        if cost is None:
            return
        with self._lock:
            self._total += float(cost)
            key = row.get("call_id")
            if key:
                self._by_call[str(key)] = self._by_call.get(str(key), 0.0) + float(cost)

    def cost_of(self, call_id: str | None) -> float | None:
        with self._lock:
            return self._by_call.get(call_id) if call_id else None

    @property
    def spent(self) -> float:
        with self._lock:
            return self._total


class Recording:
    """A ``TextModel`` that remembers the last completion its inner model returned, so a call
    that fails after the model answered (parse, validation) still has its answer. It drops the
    caller's ``accept``: the golden run scores the first answer only (no repair, no escalation)."""

    def __init__(self, inner: TextModel) -> None:
        self._inner = inner
        self.last: Completion | None = None

    @property
    def names(self) -> tuple[str, ...]:
        return self._inner.names

    def names_for(self, user: str | None) -> tuple[str, ...]:
        return self._inner.names_for(user)

    def complete(
        self,
        system: str,
        user: str,
        *,
        tag: CallTag | None = None,
        schema: Mapping[str, Any] | None = None,
        accept: Callable[[str], None] | None = None,
    ) -> Completion:
        # ``accept`` is not passed on: the run scores the FIRST answer, so an unusable one is
        # refused by the caller after the fact (``invalid``, its text kept), never repaired
        # or handed to the next provider by the chain.
        self.last = None
        self.last = self._inner.complete(system, user, tag=tag, schema=schema)
        return self.last

    def reject(self, *args: Any) -> None:
        reject = getattr(self._inner, "reject", None)
        if reject is not None:
            reject(*args)


@dataclass(frozen=True)
class CallResult:
    """One ``draft_screen`` call: ``status`` ``ok`` (a draft), ``invalid`` (the model answered,
    the draft could not be used) or ``unavailable`` (no answer); the score and fields of a
    draft; the completion's metering; the raw answer text (kept for ``--record``)."""

    provider: str
    case: str
    status: str
    passed: bool = False
    fields: frozenset[str] = frozenset()
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    latency_s: float | None = None
    cost_usd: float | None = None
    answer: str | None = None
    error: str | None = None


@dataclass
class RunResult:
    results: list[CallResult] = field(default_factory=list)
    stopped: str | None = None  # why the run ended before its plan, if it did


def evaluate(
    plan: Plan,
    models: Mapping[str, TextModel],
    draft: Draft,
    costs: CostTap,
    *,
    budget_usd: float,
    max_calls: int,
) -> RunResult:
    """Run the plan: every provider, case and repeat in turn, scoring each draft. Stops (the
    reason in ``stopped``) at ``max_calls`` calls, when ``costs`` reaches ``budget_usd``, and
    gives up on a provider after ``UNAVAILABLE_STREAK`` unavailable answers in a row."""
    run, calls = RunResult(), 0
    for provider in plan.providers:
        recording = Recording(models[provider])
        streak = 0
        for case in plan.cases:
            for _ in range(plan.repeat):
                if calls >= max_calls:
                    run.stopped = f"--max-calls {max_calls} reached"
                    return run
                if costs.spent >= budget_usd:
                    run.stopped = f"--budget-usd {budget_usd:.2f} reached (${costs.spent:.3f})"
                    return run
                if streak >= UNAVAILABLE_STREAK:
                    run.stopped = f"{provider} unavailable {UNAVAILABLE_STREAK} times in a row"
                    break
                calls += 1
                result = _call(provider, case, recording, draft, costs)
                run.results.append(result)
                streak = streak + 1 if result.status == "unavailable" else 0
            else:
                continue
            break
    return run


def _call(
    provider: str, case: GoldenCase, model: Recording, draft: Draft, costs: CostTap
) -> CallResult:
    model.last = None
    try:
        made = draft(model, case.sentence, case.current)
    except (ModelUnavailableError, ConfigurationError) as exc:
        got = model.last
        status = "invalid" if got is not None else "unavailable"
        return _result(provider, case.id, status, got, costs, error=str(exc))
    got = model.last
    graded = score(
        case,
        made.document["criteria"],
        [d.field for d in made.dropped],
        [(f.expr, f.criterion) for f in made.formulas],
        [m.key or f"new:{m.new_key_slug}" for m in made.missing],
        [u.term for u in made.unresolved],
    )
    fields = frozenset(c["field"] for c in made.document["criteria"].values())
    return _result(provider, case.id, "ok", got, costs, passed=graded.passed, fields=fields)


def _result(
    provider: str,
    case_id: str,
    status: str,
    got: Completion | None,
    costs: CostTap,
    *,
    passed: bool = False,
    fields: frozenset[str] = frozenset(),
    error: str | None = None,
) -> CallResult:
    if got is None:
        return CallResult(provider, case_id, status, error=error)
    return CallResult(
        provider, case_id, status, passed, fields, got.model, got.input_tokens,
        got.output_tokens, got.cache_read_tokens, got.cache_write_tokens, got.latency_s,
        costs.cost_of(got.call_id), got.text, error,
    )  # fmt: skip


# ------------------------------------------------------------------------------ the report


def percentile(values: Sequence[float], q: float) -> float | None:
    """The ``q`` (0..1) percentile, linear between ranks; ``None`` for no values."""
    if not values:
        return None
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def consistency(field_sets: Sequence[frozenset[str]]) -> float | None:
    """Field agreement across repeats: the mean pairwise Jaccard of the sets of fields drafted
    (1.0: every repeat drafted the same fields); ``None`` below two sets."""
    if len(field_sets) < 2:
        return None
    scores = [
        1.0 if not (a | b) else len(a & b) / len(a | b) for a, b in combinations(field_sets, 2)
    ]
    return statistics.fmean(scores)


def _mean(values: Sequence[int | None]) -> float | None:
    known = [v for v in values if v is not None]
    return statistics.fmean(known) if known else None


def measure(results: Sequence[CallResult]) -> dict[str, Any]:
    """The metrics of a group of calls (a provider's, or one of its cases)."""
    n = len(results)
    answered = [r for r in results if r.status == "ok"]
    latencies = [r.latency_s for r in results if r.latency_s is not None]
    costs = [r.cost_usd for r in results if r.cost_usd is not None]
    return {
        "calls": n,
        "pass_rate": sum(r.passed for r in results) / n if n else None,
        "consistency": consistency([r.fields for r in answered]),
        "invalid_rate": sum(r.status == "invalid" for r in results) / n if n else None,
        "unavailable": sum(r.status == "unavailable" for r in results),
        "tokens_in": _mean([r.input_tokens for r in results]),
        "tokens_out": _mean([r.output_tokens for r in results]),
        "cache_read": _mean([r.cache_read_tokens for r in results]),
        "cache_write": _mean([r.cache_write_tokens for r in results]),
        "latency_p50_s": percentile(latencies, 0.5),
        "latency_p90_s": percentile(latencies, 0.9),
        "cost_usd": sum(costs) if costs else None,
    }


def report(run: RunResult, plan: Plan) -> dict[str, Any]:
    """Everything the run measured, by provider, then case (``--json`` prints this)."""
    out: dict[str, Any] = {"stopped": run.stopped, "planned_calls": plan.calls, "providers": {}}
    for provider in plan.providers:
        mine = [r for r in run.results if r.provider == provider]
        out["providers"][provider] = {
            "models": sorted({r.model for r in mine if r.model}),
            "summary": measure(mine),
            "cases": {
                c.id: measure([r for r in mine if r.case == c.id])
                for c in plan.cases
                if any(r.case == c.id for r in mine)
            },
        }
    return out


def _fmt(value: float | None, spec: str) -> str:
    return "-" if value is None else format(value, spec)


def _row(label: str, m: Mapping[str, Any]) -> str:
    return (
        f"{label:<34} {m['calls']:>5} {_fmt(m['pass_rate'], '.0%'):>6} "
        f"{_fmt(m['consistency'], '.2f'):>6} {_fmt(m['invalid_rate'], '.0%'):>7} "
        f"{m['unavailable']:>5} {_fmt(m['tokens_in'], '.0f'):>7} {_fmt(m['tokens_out'], '.0f'):>6} "
        f"{_fmt(m['cache_read'], '.0f'):>7} {_fmt(m['cache_write'], '.0f'):>7} "
        f"{_fmt(m['latency_p50_s'], '.1f'):>6} {_fmt(m['latency_p90_s'], '.1f'):>6} "
        f"{_fmt(m['cost_usd'], '.4f'):>8}"
    )


HEADER = (
    f"{'provider / case':<34} {'calls':>5} {'pass':>6} {'consis':>6} {'invalid':>7} {'unav.':>5} "
    f"{'in':>7} {'out':>6} {'c.read':>7} {'c.write':>7} {'p50 s':>6} {'p90 s':>6} {'USD':>8}"
)


def report_lines(rep: Mapping[str, Any]) -> list[str]:
    """The report as text: one block per provider (its summary, then its cases), then the
    summary table of the providers."""
    lines: list[str] = []
    for provider, data in rep["providers"].items():
        lines += ["", f"{provider} ({', '.join(data['models']) or 'no answer'})", HEADER]
        lines += [_row(f"  {cid}", m) for cid, m in data["cases"].items()]
        lines.append(_row("  TOTAL", data["summary"]))
    lines += ["", "summary", HEADER]
    lines += [_row(p, d["summary"]) for p, d in rep["providers"].items()]
    if rep["stopped"]:
        lines.append(f"STOPPED EARLY: {rep['stopped']}")
    return lines


# ------------------------------------------------------------------------------ --record


def slug(model: str) -> str:
    """A directory name for a model id (``gemini-3-flash``, ``claude-haiku-4-5``)."""
    return re.sub(r"[^a-z0-9._-]+", "-", model.lower()).strip("-") or "model"


def recordings(run: RunResult, root: Path) -> list[tuple[Path, str]]:
    """The (path, raw answer) to write: per model and case, the first answer that passed."""
    chosen: dict[Path, str] = {}
    for r in run.results:
        if r.passed and r.model and r.answer is not None:
            chosen.setdefault(root / "answers" / slug(r.model) / f"{r.case}.json", r.answer)
    return sorted(chosen.items())


def write_recordings(
    items: Sequence[tuple[Path, str]], *, force: bool, say: Callable[[str], None]
) -> int:
    """Say what will be written, then write it; a file that exists stays unless ``force``.
    -> the number of files written."""
    written = 0
    for path, text in items:
        if path.exists() and not force:
            say(f"skip (exists, use --force): {path}")
            continue
        say(f"write: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text.endswith("\n") else text + "\n")
        mark_recorded(path.parents[2], path.stem)  # answers/<slug>/<id>.json -> the case file
        written += 1
    return written


# ------------------------------------------------------------------------------ the command


@dataclass(frozen=True)
class RunArgs:
    cases: tuple[str, ...] = ()
    split: str = "all"
    providers: tuple[str, ...] = ()
    repeat: int = DEFAULT_REPEAT
    record: bool = False
    force: bool = False
    as_json: bool = False
    max_calls: int = DEFAULT_MAX_CALLS
    budget_usd: float = DEFAULT_BUDGET_USD
    yes: bool = False


def run_golden(
    args: RunArgs,
    settings: LlmSettings,
    switch_off: bool,
    root: Path,
    open_models: Callable[[Sequence[str], CostTap], Mapping[str, TextModel]],
    draft: Draft,
    say: Callable[[str], None],
    note: Callable[[str], None],
) -> int:
    """The command: refuse, plan, require ``--yes``, run, report, record. ``say`` gets the
    report (what ``--json`` makes machine-readable), ``note`` everything else (the CLI sends it
    to stderr with ``--json``). -> the exit code (0 done, 1 refused or not confirmed, 2 a bad
    argument)."""
    if switch_off or not settings.enabled:
        note(
            "refused: the text model is off. Enable it: unset ALGOTRADE_LLM (it is `off`) and "
            "set `enabled = true` in config/site/llm.toml (or your llm.local.toml), with each "
            "remote provider's key in ALGOTRADE_LLM_API_KEY_<ID>."
        )
        return 1
    try:
        cases = select_cases(load_cases(root), args.cases or None, args.split)
        providers = args.providers or tuple(p.id for p in settings.providers)
        plan = make_plan(settings, cases, providers, args.repeat, args.max_calls)
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
        models = open_models(providers, costs)
    except ConfigurationError as exc:
        note(f"refused: {exc}")
        return 2
    run = evaluate(plan, models, draft, costs, budget_usd=args.budget_usd, max_calls=args.max_calls)
    rep = report(run, plan)
    say(json.dumps(rep, indent=2) if args.as_json else "\n".join(report_lines(rep)))
    if args.record:
        write_recordings(recordings(run, root), force=args.force, say=note)
    return 0
