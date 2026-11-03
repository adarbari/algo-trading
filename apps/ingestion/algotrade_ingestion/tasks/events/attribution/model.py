"""The model source of the ``attribution`` task (ADR 0050 decision 5, EV4b): the headlines of the
night's big movers that have no 8-K cause, classified through the text model into
``source = "model"`` rows of ``events/attribution``.

For at most ``news_per_night`` (``events/attribution.toml``) movers (the movers of the run session
with no filing row, in instrument id order: the same names on a rerun), one Massive news request
for the headlines published after the previous close and by the reaction session's close (so none
a trader could not have read by then), and one model call. The answer is checked
(``services.attributing .headlines``): a cause outside the taxonomy, a headline that was not
shown, or text that is not the JSON asked for stores nothing and is counted. The model is the
site's own chain: a provider with ``only_users`` (the owner's Claude login) is never built here,
the text model off (``llm.toml``, ``ALGOTRADE_LLM=off``), no Massive key or ``news_per_night = 0``
skip the source with the reason, and the filing rows are unaffected. A row's ``known_from`` is the
session the task ran on."""

from collections import Counter
from datetime import UTC, date

from algotrade.config.site.events.attribution import load_attribution
from algotrade.core.model.completion import CallTag
from algotrade.core.model.errors import DailyLimitError, ModelUnavailableError, RateLimitedError
from algotrade.core.time.calendar import close_time, previous_session
from algotrade.services.attributing import headlines
from algotrade.services.text_model.model import TextModel
from algotrade_ingestion.tasks.framework.run import IngestRun, NoResponseError, TaskContext
from algotrade_sources.framework.series import NEWS_FRAME, NewsRequest

SOURCE = "model"
SOURCES_KEY = "massive_news"
USE_CASE = "attributing"
STOPS = (ModelUnavailableError, RateLimitedError, DailyLimitError)


def _instant(day: date) -> str:
    return close_time(day).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def skipped(ctx: TaskContext) -> str | None:
    """Why the model source cannot run at all, else None."""
    if load_attribution(ctx.configs).news_per_night <= 0:
        return "events/attribution.toml news_per_night is 0"
    if ctx.sources.get(SOURCES_KEY) is None:
        return ctx.unavailable.get(SOURCES_KEY, f"{SOURCES_KEY} is not built")
    if ctx.text_model_factory is None:
        return "no text model is wired into this run"
    return None


def classify(
    run: IngestRun,
    ctx: TaskContext,
    model: TextModel,
    iid: str,
    symbol: str,
    session: date,
    window: tuple[str, str],
    dropped: Counter[str],
) -> tuple[dict[str, object] | None, bool, bool]:
    """``(row, asked, stop)`` of one mover: its headlines, the model's checked answer; ``stop``
    when the chain is down or the budget spent (no more calls tonight)."""
    request = NewsRequest(
        key=symbol,
        instrument_id=iid,
        session_date=session,
        start=window[0],
        end=window[1],
        limit=headlines.MAX_HEADLINES,
    )
    try:
        normalized = run.fetch(ctx.sources[SOURCES_KEY], request)
    except NoResponseError:
        dropped["no news response"] += 1
        return None, True, False
    shown = headlines.headlines_of(normalized.parsed[NEWS_FRAME] if normalized else None)
    if not shown:
        dropped["no headlines"] += 1
        return None, True, False
    tag = CallTag(USE_CASE, ctx.user, headlines.PROMPT_VERSION)
    try:
        done = model.complete(headlines.SYSTEM, headlines.prompt(symbol, session, shown), tag=tag)
    except STOPS as error:
        dropped[f"model: {type(error).__name__}"] += 1
        return None, True, True
    answer = headlines.parse_answer(done.text, shown)
    if isinstance(answer, str):
        dropped[answer] += 1
        return None, True, False
    label = f"{done.provider}:{done.model}"
    return headlines.attribution_row(iid, session, session, answer, label), True, False


def attribute_with_model(
    run: IngestRun, ctx: TaskContext, session: date, movers: list[str]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """``(rows, stats)`` for ``movers`` (instrument ids; at most ``news_per_night`` are asked)."""
    why = skipped(ctx)
    model: TextModel | None = None
    if why is None:
        assert ctx.text_model_factory is not None
        model, off = ctx.text_model_factory()
        why = None if model is not None else off
    if why is not None or model is None:
        run.record_item("model", f"SKIPPED: {why}")
        return [], {"skipped": why}
    names = run.resolver(session).symbols  # instrument id -> ticker (the reference snapshot)
    window = (_instant(previous_session(session)), _instant(session))
    rows: list[dict[str, object]] = []
    dropped: Counter[str] = Counter()
    asked = 0
    try:
        for iid in movers[: load_attribution(ctx.configs).news_per_night]:
            if iid not in names:
                dropped["no symbol"] += 1
                continue
            row, was_asked, stop = classify(
                run, ctx, model, iid, str(names[iid]), session, window, dropped
            )
            asked += was_asked
            if row is not None:
                rows.append(row)
            if stop:
                break
    finally:
        close = getattr(model, "close", None)
        if close is not None:
            close()  # flush the usage the ledger queued (usage/llm_calls)
    run.record_item("model", f"OK: {asked} asked, {len(rows)} attributed")
    return rows, {"asked": asked, "stored": len(rows), "dropped": dict(dropped)}
