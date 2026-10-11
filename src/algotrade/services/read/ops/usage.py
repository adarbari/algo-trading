"""``LlmUsage`` for the Admin "LLM usage & cost" page: what the text model spent, read from the
usage log (``usage/llm_calls``, ADR 0058) over a **date range** ending at the exchange calendar
date ``today`` (ADR 0058 states this read as an exception to ADR 0036's one-session rule: spend
is a time series, not a fact of one session, so it ignores ``ctx.session`` and reads no session
partition).

Four windows (today, 7 days, 30 days, month to date) with the budget cap of ``llm.toml`` and the
share used (a day or a month has a cap; 7 and 30 days none; no cap set: ``limit_usd`` None), the
30 days broken down by model, use case, user, cost basis and outcome, a daily series, the
fallback / failure rates, the latest calls and the latest failures (a provider that raised, or
an answer the caller rejected, with the message, the prompt and the raw answer: ADR 0058
amended 2026-10-11). ``spent_usd`` is what counts against the budget
(``price`` + ``reported`` + ``bound``, as the ledger counts it); ``reported_usd`` is the notional
seat cost of a ``claude-cli`` login, shown beside, never merged into ``billed_usd`` (``price``).
Tokens a provider did not report are never 0: a sum is of the calls that did, ``calls_without_
tokens`` counts the rest and ``unknown`` says so when none did."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from algotrade.config.site.settings import load_llm
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.time.calendar import exchange_date
from algotrade.data.usage import LLM_CALLS, SPENDING, read_llm_calls
from algotrade.services.read.availability.cause import table_cause
from algotrade.services.read.context import Stores
from algotrade.services.read.values import Unknown, UnknownCode, to_scalar

DAYS = 30  # the span of the breakdowns, the daily series and the recent calls
WEEK = 7
RECENT = 50
OUTCOMES = ("ok", "fell_back", "failed", "skipped_budget", "rejected")
SKIPPED = "skipped_budget"
REJECTED = "rejected"
FAILURES = ("failed", "rejected")  # the outcomes the failures list holds
COLUMNS = (
    "ts", "day", "provider", "model", "use_case", "user", "input_tokens", "output_tokens",
    "latency_s", "cost_usd", "cost_basis", "outcome", "fell_back_from", "run_id",
    "error", "stage", "sentence", "answer", "prompt_chars",
)  # fmt: skip
ADDED = ("error", "stage", "sentence", "answer", "prompt_chars")  # absent in older partitions


@dataclass(frozen=True)
class Tally:
    """The calls of a slice: ``calls`` attempts; tokens summed over the calls that reported them
    (``calls_without_tokens`` the others, skipped attempts aside; ``unknown`` set when none
    reported); ``spent_usd`` what counts against the budget, split into ``billed_usd``
    (``price``), ``reported_usd`` (notional seat cost) and ``bound_usd`` (an upper bound charged
    for an unknown cost); ``free_calls`` the ones logged at 0."""

    calls: int
    input_tokens: int
    output_tokens: int
    calls_without_tokens: int
    spent_usd: float
    billed_usd: float
    reported_usd: float
    bound_usd: float
    free_calls: int
    unknown: Unknown | None = None


@dataclass(frozen=True)
class Cap:
    """A budget cap: ``kind`` daily or monthly, ``limit_usd`` None when none is set, ``used_share``
    spent / limit (above 1: over it), None without a cap."""

    kind: str
    limit_usd: float | None
    used_share: float | None


@dataclass(frozen=True)
class Window:
    """``key`` today, 7d, 30d or month, over ``start``..``end``; ``cap`` None for a window
    with no cap of its own (7d, 30d)."""

    key: str
    start: date
    end: date
    tally: Tally
    cap: Cap | None


@dataclass(frozen=True)
class Slice:
    """One group of a breakdown (``key`` None: the stored value is null; ``provider`` set for
    the model breakdown); ``cost_share`` its share of the 30 days' ``spent_usd`` (None: none)."""

    key: str | None
    provider: str | None
    tally: Tally
    cost_share: float | None


@dataclass(frozen=True)
class Breakdown:
    """The 30 days by ``by``: model, use_case, user, cost_basis or outcome, most spent first."""

    by: str
    rows: tuple[Slice, ...]


@dataclass(frozen=True)
class DayPoint:
    day: date
    tally: Tally


@dataclass(frozen=True)
class Reliability:
    """Attempts of the 30 days and how they ended; a rate is None when there are no attempts.
    ``fallback_rate`` is ``fell_back`` / attempts, ``failure_rate`` ``failed`` / attempts;
    ``rejected`` counts the answers a caller could not use: a second row of an ``ok`` attempt,
    shown on its own and left out of ``attempts`` and the rates."""

    attempts: int
    ok: int
    fell_back: int
    failed: int
    skipped_budget: int
    rejected: int
    fallback_rate: float | None
    failure_rate: float | None


@dataclass(frozen=True)
class Call:
    """One stored attempt, newest first; ``unknown_fields`` names the values stored null (with
    ``unknown`` saying why): tokens a provider did not report, a cost not known. A failure
    (``failed``, ``rejected``) also holds ``stage`` (``provider`` / ``answer``), ``error``, the
    prompt (``sentence``) and the raw ``answer``; ``prompt_chars`` the prompt's length. Null on
    every other call and on a call recorded before they were kept."""

    ts: datetime
    provider: str
    model: str
    use_case: str
    user: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_s: float | None
    cost_usd: float | None
    cost_basis: str
    outcome: str
    fell_back_from: str | None
    run_id: str
    error: str | None
    stage: str | None
    sentence: str | None
    answer: str | None
    prompt_chars: int | None
    unknown_fields: tuple[str, ...]
    unknown: Unknown | None


@dataclass(frozen=True)
class BudgetInfo:
    """``[budget]`` of ``llm.toml`` (a cap None: not set); ``error`` the words of an unreadable
    file (then no caps are known)."""

    daily_usd: float | None
    monthly_usd: float | None
    over: str | None
    reported_call_usd: float | None
    error: str | None


@dataclass(frozen=True)
class LlmUsage:
    """The usage page: ``recorded`` False when the log holds nothing in the 30 days / month;
    ``failures`` the newest failed or rejected calls of the 30 days (at most ``recent``)."""

    today: date
    recorded: bool
    budget: BudgetInfo
    windows: tuple[Window, ...]
    breakdowns: tuple[Breakdown, ...]
    daily: tuple[DayPoint, ...]
    reliability: Reliability
    recent: tuple[Call, ...]
    failures: tuple[Call, ...]


def load_llm_usage(ctx: Stores, today: date | None = None, recent: int = RECENT) -> LlmUsage:
    """The usage of the text model up to ``today`` (default: the exchange date now)."""
    today = today or exchange_date(datetime.now(UTC))
    month = today.replace(day=1)
    span = today - timedelta(days=DAYS - 1)
    frame = _prepared(read_llm_calls(ctx.reader, min(span, month), today))
    budget = _budget(ctx)
    last = frame[frame["day"] >= span]
    newest = last.sort_values("ts", ascending=False).head(recent)
    failed = last[last["outcome"].isin(FAILURES)].sort_values("ts", ascending=False).head(recent)
    windows = (
        _window("today", today, today, frame, Cap("daily", budget.daily_usd, None)),
        _window("7d", today - timedelta(days=WEEK - 1), today, frame, None),
        _window("30d", span, today, frame, None),
        _window("month", month, today, frame, Cap("monthly", budget.monthly_usd, None)),
    )
    return LlmUsage(
        today=today,
        recorded=not frame.empty,
        budget=budget,
        windows=windows,
        breakdowns=_breakdowns(last),
        daily=tuple(DayPoint(d, _tally(last[last["day"] == d])) for d in _days(span, today)),
        reliability=_reliability(last),
        recent=tuple(_call(r) for r in newest.to_dict("records")),
        failures=tuple(_call(r) for r in failed.to_dict("records")),
    )


def _prepared(stored: pd.DataFrame | None) -> pd.DataFrame:
    """The log with its exchange date as ``day`` (an empty frame with the columns: nothing)."""
    if stored is None or stored.empty:
        return pd.DataFrame(columns=list(COLUMNS))
    # partitions written before the failure columns existed read them as null
    missing = {c: None for c in ADDED if c not in stored.columns}
    return stored.assign(day=pd.to_datetime(stored["session_date"]).dt.date, **missing)


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _budget(ctx: Stores) -> BudgetInfo:
    try:
        b = load_llm(ctx.configs).budget
    except ConfigurationError as e:
        return BudgetInfo(None, None, None, None, str(e))
    return BudgetInfo(b.daily_usd, b.monthly_usd, b.over, b.reported_call_usd, None)


def _window(key: str, start: date, end: date, frame: pd.DataFrame, cap: Cap | None) -> Window:
    tally = _tally(frame[(frame["day"] >= start) & (frame["day"] <= end)])
    if cap is not None and cap.limit_usd is not None:
        # a cap of 0 is a cap: the ledger refuses every paid call, so it reads as fully used
        share = tally.spent_usd / cap.limit_usd if cap.limit_usd > 0 else 1.0
        cap = Cap(cap.kind, cap.limit_usd, share)
    return Window(key, start, end, tally, cap)


def _cost(frame: pd.DataFrame, *bases: str) -> float:
    rows = frame[frame["cost_basis"].isin(bases) & frame["cost_usd"].notna()]
    return float(rows["cost_usd"].sum())


def _tokens(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].astype("float64").sum())  # null (unknown) adds nothing


def _tally(frame: pd.DataFrame) -> Tally:
    frame = frame[frame["outcome"] != REJECTED]  # its ok row is the call: never counted twice
    made = frame[frame["outcome"] != SKIPPED]  # a skipped attempt asked nothing: no tokens due
    without = int(made["input_tokens"].isna().sum())
    unknown = None
    if len(made) and without == len(made):
        unknown = Unknown(
            UnknownCode.NULL,
            table_cause(LLM_CALLS, "no call of this slice reported its tokens", "NULL"),
        )
    return Tally(
        calls=len(frame),
        input_tokens=_tokens(frame, "input_tokens"),
        output_tokens=_tokens(frame, "output_tokens"),
        calls_without_tokens=without,
        spent_usd=_cost(frame, *SPENDING),
        billed_usd=_cost(frame, "price"),
        reported_usd=_cost(frame, "reported"),
        bound_usd=_cost(frame, "bound"),
        free_calls=int((frame["cost_basis"] == "free").sum()),
        unknown=unknown,
    )


def _breakdowns(frame: pd.DataFrame) -> tuple[Breakdown, ...]:
    frame = frame[frame["outcome"] != REJECTED]  # a rejected row is no call of its own
    total = _cost(frame, *SPENDING)
    out = [Breakdown("model", _slices(frame, ["model", "provider"], total))]
    out += [Breakdown(c, _slices(frame, [c], total)) for c in BY]
    return tuple(out)


BY = ("use_case", "user", "cost_basis", "outcome")


def _slices(frame: pd.DataFrame, columns: list[str], total: float) -> tuple[Slice, ...]:
    if frame.empty:
        return ()
    rows: list[Slice] = []
    for keys, part in frame.groupby(columns, dropna=False, sort=False):
        values = keys if isinstance(keys, tuple) else (keys,)
        key = to_scalar(values[0])
        tally = _tally(part)
        provider = str(values[1]) if len(values) > 1 else None
        share = tally.spent_usd / total if total else None
        rows.append(Slice(None if key is None else str(key), provider, tally, share))
    return tuple(sorted(rows, key=lambda s: (-s.tally.spent_usd, -s.tally.calls, s.key or "")))


def _reliability(frame: pd.DataFrame) -> Reliability:
    count = {o: int((frame["outcome"] == o).sum()) for o in OUTCOMES}
    n = len(frame) - count[REJECTED]  # a rejected row is a second row of an ok attempt
    return Reliability(
        n, count["ok"], count["fell_back"], count["failed"], count[SKIPPED], count["rejected"],
        count["fell_back"] / n if n else None, count["failed"] / n if n else None,
    )  # fmt: skip


def _text(value: Any) -> str | None:
    scalar = to_scalar(value)
    return None if scalar is None else str(scalar)


def _number(value: Any, kind: type) -> Any:
    scalar = to_scalar(value)
    return None if scalar is None else kind(scalar)


def _call(row: Mapping[Any, Any]) -> Call:
    tokens_in, tokens_out = _number(row["input_tokens"], int), _number(row["output_tokens"], int)
    cost = _number(row["cost_usd"], float)
    named = (("input_tokens", tokens_in), ("output_tokens", tokens_out), ("cost_usd", cost))
    missing = tuple(name for name, value in named if value is None)
    why = (
        "the attempt was skipped: nothing was asked, nothing spent"
        if row["outcome"] == SKIPPED
        else "the provider did not report it"
    )
    return Call(
        ts=pd.Timestamp(row["ts"]).to_pydatetime(),
        provider=str(row["provider"]),
        model=str(row["model"]),
        use_case=str(row["use_case"]),
        user=_text(row["user"]),
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        latency_s=_number(row["latency_s"], float),
        cost_usd=cost,
        cost_basis=str(row["cost_basis"]),
        outcome=str(row["outcome"]),
        fell_back_from=_text(row["fell_back_from"]),
        run_id=str(row["run_id"]),
        error=_text(row["error"]),
        stage=_text(row["stage"]),
        sentence=_text(row["sentence"]),
        answer=_text(row["answer"]),
        prompt_chars=_number(row["prompt_chars"], int),
        unknown_fields=missing,
        unknown=Unknown(UnknownCode.NULL, table_cause(LLM_CALLS, why, "NULL")) if missing else None,
    )
