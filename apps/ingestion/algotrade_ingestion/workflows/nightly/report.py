"""The nightly summary report: high-level statistics and a failure deep dive (pure).

``build_report`` turns a nightly summary (``nightly.run_nightly``'s dict, or one rebuilt from
stored run records by ``records.stored_summary``) plus the task run records of those steps
into a ``Report``: one ``StepLine`` per step (status, duration, key counts, per-item status
counts), failed items grouped by normalised reason with a few examples each, failed quality
checks, screen coverage gaps, the live verification against IBKR and short "what to do"
hints. ``render.py`` turns it into text
and HTML; ``notify.py`` mails it.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from algotrade.services.run_items import failed_items, normalise, status_code
from algotrade.storage.runs import RunRecord
from algotrade_ingestion.workflows.nightly.timing import (
    ArrivalStat,
    PacingLine,
    StepTiming,
    step_timings,
    vendor_pacing,
)

BAD_STEPS = ("FAILED", "NOT_RUN", "WAITING", "PARTIAL", "BLOCKED")  # PARTIAL / BLOCKED: before 0039
# Key counts per step (result keys); other steps show their top-level numbers.
KEY_COUNTS: Mapping[str, tuple[str, ...]] = {
    "universe-build": ("covered", "delisted_carried"),
    "company-details": ("rows", "requested", "fetched", "failed_count", "deferred_by_limit"),
    "shares": ("rows", "requested", "with_facts", "no_facts", "failed_count", "deferred_by_limit"),
    "etf-holdings": ("rows", "requested", "read", "no_file", "rejected", "deferred_by_limit"),
    "earnings": ("rows", "companies", "reported", "unresolved"),
    "rates": ("curves", "latest"),
    "corporate-actions": ("events/split", "events/dividend", "unresolved"),
    "chains": ("universe",),
    "ibkr-contracts": (
        "underlyings",
        "resolved",
        "coverage_pct",
        "refreshed",
        "not_found",
        "deferred",
    ),
    "ibkr-iv": (
        "underlyings",
        "with_iv",
        "coverage_pct",
        "backfilled",
        "backfill_pending",
        "backfill_eta_h",
    ),
    "purge-raw": ("raw_files_removed", "staging_runs_removed"),
}
COUNT_MAPS = ("statuses", "sessions", "years")  # result dicts of status -> count
MAX_GENERIC = 6


@dataclass(frozen=True)
class Example:
    key: str  # the run record's item key (instrument id, CIK, date, check)
    message: str
    label: str | None = None  # the ticker, when the key is an instrument id


@dataclass(frozen=True)
class FailureGroup:
    session: str
    step: str
    reason: str  # normalised: code + message without ids, URLs, dates or numbers
    count: int
    examples: tuple[Example, ...]


@dataclass(frozen=True)
class StepLine:
    session: str  # "" for steps that run once after every session (purge-raw)
    step: str
    status: str
    duration_s: float
    counts: tuple[tuple[str, Any], ...] = ()  # key counts from the step result
    items: tuple[tuple[str, int], ...] = ()  # per-item status counts, most common first
    note: str = ""  # why it FAILED, was NOT_RUN, SKIPPED or WAIVED, or its error


@dataclass(frozen=True)
class Check:
    session: str
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class ScreenLine:
    session: str
    config: str
    status: str
    coverage_pct: float | None
    decisions: tuple[tuple[str, int], ...]
    gaps: tuple[tuple[str, int], ...]  # normalised skipped reason -> count
    error: str = ""


@dataclass(frozen=True)
class VerificationLine:
    """The ``verify`` step of a session: checks by status, failing examples, or why skipped."""

    session: str
    status: str  # the step status
    instruments: int
    counts: tuple[tuple[str, int], ...]  # PASS / WARN / FAIL / NA
    examples: tuple[str, ...]  # "AAPL close FAIL: ours 1.0 vs IBKR 2.0 (note)"
    note: str = ""  # SKIPPED reason or step error


@dataclass(frozen=True)
class CoverageLine:
    """One feature in one tier for a session (the ``coverage_*`` check of the rollups step):
    ``covered`` of ``applicable`` names have it, ``previous`` the share the session before."""

    session: str
    feature: str
    tier: str
    applicable: int
    covered: int
    share: float | None
    previous: float | None
    ok: bool  # within its minimum and its day-over-day drop
    missing: tuple[str, ...]  # symbols of a failing cell, at most max_examples


@dataclass(frozen=True)
class Report:
    sessions: tuple[str, ...]
    status: str
    started: datetime | None
    finished: datetime | None
    duration_s: float
    warnings: tuple[str, ...]
    steps: tuple[StepLine, ...]
    failures: tuple[FailureGroup, ...]
    checks: tuple[Check, ...]  # acceptance checks that did not PASS
    screens: tuple[ScreenLine, ...]
    rollups: tuple[tuple[str, str, int, int], ...]  # session, rollup, rows, no_input sessions
    hints: tuple[str, ...] = field(default=())
    timings: tuple[StepTiming, ...] = ()  # run timing per step (timing.py)
    arrivals: tuple[ArrivalStat, ...] = ()  # when each source-fed step's data first appeared
    pacing: tuple[PacingLine, ...] = ()  # vendor limiters per step (requests, 429s, waits)
    max_duration_s: float | None = None  # [alerts] max_duration_minutes
    catch_up_held: tuple[str, ...] = ()  # sessions held back behind a failed one
    catch_up_waiting: tuple[str, ...] = ()  # pending sessions over the cap, for the next run
    verification: tuple[VerificationLine, ...] = ()  # the verify step per session
    coverage: tuple[CoverageLine, ...] = ()  # feature x tier coverage per session (ADR 0043)

    @property
    def bad_steps(self) -> tuple[StepLine, ...]:
        return tuple(s for s in self.steps if s.status in BAD_STEPS)

    def chains_ok(self) -> int | None:
        counts = [dict(s.items).get("OK") for s in self.steps if s.step == "chains"]
        known = [c for c in counts if c is not None]
        return known[-1] if known else None

    def subject(self) -> str:
        """``[algotrade] 2026-10-02 nightly: SUCCEEDED · chains 3,624 OK · 0 failures``."""
        ends = (self.sessions[0], self.sessions[-1]) if self.sessions else ()
        when = "..".join(dict.fromkeys(ends)) or "no session"
        parts = [f"[algotrade] {when} nightly: {self.status}"]
        chains = self.chains_ok()
        if chains is not None:
            parts.append(f"chains {chains:,} OK")
        bad = len(self.bad_steps)
        parts.append(f"{bad} steps with failures" if bad else "0 failures")
        return " · ".join(parts)


def _counts(name: str, result: Any) -> tuple[tuple[str, Any], ...]:
    if not isinstance(result, Mapping):
        return ()
    if name == "screens":
        return (("screens", len(result.get("screens", []))),)
    if name == "edge-signals":
        return (("users", len(result.get("signals", []))),)
    rollups = [v for k, v in result.items() if "@" in k and isinstance(v, Mapping)]
    if rollups:
        return (("rollups", len(rollups)), ("rows", sum(int(v.get("rows", 0)) for v in rollups)))
    keys = KEY_COUNTS.get(name)
    if keys is None:
        keys = tuple(
            k
            for k, v in result.items()
            if isinstance(v, int | float | str) and not isinstance(v, bool)
        )[:MAX_GENERIC]
    return tuple((k, result[k]) for k in keys if k in result)


def _items(record: RunRecord | None, result: Any) -> tuple[tuple[str, int], ...]:
    if record is not None and record.items:
        return tuple(Counter(status_code(v) for v in record.items.values()).most_common())
    if isinstance(result, Mapping):
        for key in COUNT_MAPS:
            value = result.get(key)
            if isinstance(value, Mapping):
                pairs = [(str(k), int(v)) for k, v in value.items()]
                return tuple(sorted(pairs, key=lambda kv: -kv[1]))
    return ()


def _groups(
    session: str,
    step: str,
    record: RunRecord,
    labels: Mapping[str, str],
    max_examples: int,
) -> list[FailureGroup]:
    return [
        FailureGroup(
            session,
            step,
            reason,
            len(items),
            tuple(Example(k, s, labels.get(k)) for k, s in items[:max_examples]),
        )
        for reason, items in failed_items(record.items)
    ]


def _screens(session: str, result: Any) -> list[ScreenLine]:
    out = []
    for screen in (result or {}).get("screens", []) if isinstance(result, Mapping) else []:
        gaps: Counter[str] = Counter()
        for reason, count in (screen.get("skipped_reasons") or {}).items():
            gaps[normalise(str(reason))] += int(count)
        decisions = screen.get("decisions") or {}
        out.append(
            ScreenLine(
                session,
                str(screen.get("config", "?")),
                str(screen.get("status", "?")),
                screen.get("coverage_pct"),
                tuple(
                    sorted(((str(k), int(v)) for k, v in decisions.items()), key=lambda x: -x[1])
                ),
                tuple(gaps.most_common()),
                str(screen.get("error") or ""),
            )
        )
    return out


def _rollups(session: str, result: Any) -> list[tuple[str, str, int, int]]:
    if not isinstance(result, Mapping):
        return []
    return [
        (session, name, int(v.get("rows", 0)), int(v.get("no_input", 0)))
        for name, v in result.items()
        if "@" in name and isinstance(v, Mapping)
    ]


def _value(value: Any) -> str:
    return f"{value:.6g}" if isinstance(value, int | float) else "-"


def _verification(session: str, step: Mapping[str, Any]) -> list[VerificationLine]:
    result = step.get("result")
    stats = result if isinstance(result, Mapping) else {}
    found = stats.get("checks")
    counts: Mapping[str, Any] = found if isinstance(found, Mapping) else {}
    examples = tuple(
        f"{e.get('symbol')} {e.get('check')} {e.get('status')}: ours {_value(e.get('ours'))} "
        f"vs IBKR {_value(e.get('theirs'))} ({e.get('note', '')})"
        for e in stats.get("failing", [])
        if isinstance(e, Mapping)
    )
    note = str(step.get("error") or step.get("reason") or "")
    return [
        VerificationLine(
            session,
            str(step.get("status")),
            int(stats.get("instruments", 0)),
            tuple((str(k), int(v)) for k, v in counts.items()),
            examples,
            note,
        )
    ]


def _checks(session: str, holder: Any) -> list[Check]:
    checks = holder.get("checks", []) if isinstance(holder, Mapping) else []
    return [
        Check(session, str(c.get("name")), str(c.get("status")), str(c.get("detail", "")))
        for c in checks
        if isinstance(c, Mapping) and c.get("status") != "PASS"
    ]


def _coverage(session: str, step: Mapping[str, Any], max_examples: int) -> list[CoverageLine]:
    """The cells of the step's ``coverage_<feature>`` checks (their stored ``data``)."""
    out = []
    for c in step.get("checks", []) if isinstance(step, Mapping) else []:
        name = str(c.get("name", ""))
        if not name.startswith("coverage_") or not isinstance(c.get("data"), Mapping):
            continue
        for cell in c["data"].get("cells", []):
            ok = bool(cell.get("ok", True))
            missing = tuple(str(m) for m in cell.get("missing", []))
            out.append(
                CoverageLine(
                    session,
                    name.removeprefix("coverage_"),
                    str(cell.get("tier")),
                    int(cell.get("applicable", 0)),
                    int(cell.get("covered", 0)),
                    cell.get("share"),
                    cell.get("previous"),
                    ok,
                    () if ok else missing[:max_examples],
                )
            )
    return out


def _steps(summary: Mapping[str, Any]) -> Iterable[tuple[str, str, Mapping[str, Any]]]:
    for run in summary.get("runs", []):
        for name, step in run.get("steps", {}).items():
            yield run["session"], name, step
    for name, step in summary.get("steps", {}).items():
        yield "", name, step


def _parse(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) and value else None


# "What to do" for known failure kinds: (pattern searched in reasons, errors and checks, hint).
HINTS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.IGNORECASE), h)
    for p, h in (
        (
            r"circuit",
            "Circuit breaker open: the vendor is blocking or throttling us. Check "
            "pacing (sources.toml min_interval_s) and re-run the step later.",
        ),
        (
            r"HTTP 40[13]\b",
            "HTTP 401/403: the API key was rejected or the plan does not cover "
            "the endpoint. Check the key in .env and the vendor plan.",
        ),
        (r"HTTP 429\b", "HTTP 429: rate limited. Raise min_interval_s for that vendor."),
        (
            r"HTTP 5\d\d\b|timed? ?out|Connection",
            "Vendor or network errors: usually transient; "
            "re-run the step (`algotrade-ingest run <task> --date D`).",
        ),
        (
            r"^STALE_DATA",
            "STALE_DATA: Cboe served an older chain (thin delayed data for illiquid "
            "names). Usually clears on the next run; a large share means a feed problem.",
        ),
        (
            r"^NO_CHAIN",
            "NO_CHAIN: flagged optionable but Cboe has no chain (delisted, renamed or "
            "options not listed yet).",
        ),
        (
            r"duplicate rows for the table key",
            "Duplicate table keys: a producer wrote the same "
            "key twice. Fix the producing task, then re-run it for the session.",
        ),
        (
            r"companyfacts document has no CIK",
            "SEC companyfacts without a CIK: SEC returned an "
            "unexpected document (merged or retired CIK); retried on the next refresh.",
        ),
        (
            r"is not configured|credential|API key",
            "A source is not configured: set its credential in .env (see .env.example).",
        ),
        (
            r"^chains_fetch",
            "chains_fetch: too many chains failed to fetch (FETCH_ERROR incl. an open circuit, "
            "NOT_ATTEMPTED, or STALE_CHRONIC: STALE_DATA for over [quality] "
            "max_chain_stale_sessions sessions) above [quality] max_chain_fetch_failures. Check "
            "the Cboe circuit and pacing, then re-run `algotrade-ingest chains --date D` (it "
            "resumes); STALE_CHRONIC names the feed no longer serves.",
        ),
        (
            r"^chains_stale",
            "chains_stale_core / chains_stale_rest: STALE_DATA share of the tier above [quality] "
            "max_chain_stale_share_core (S&P 500, priority symbols, HIGH liquidity) or "
            "max_chain_stale_share (the rest): Cboe served older chains (thin delayed data). "
            "Re-run chains later; screens treat them as UNKNOWN.",
        ),
        (
            r"IB Gateway not reachable|\[ibkr\] is disabled",
            "IBKR steps (verify, ibkr-contracts, ibkr-iv) skipped: start IB Gateway (Read-Only "
            "API ticked, port as in .env ALGOTRADE_IBKR_PORT) and set [ibkr] enabled = true; "
            "README, Live verification. iv_rank falls back to ours (iv_rank_source = ours).",
        ),
        (
            r"^verification",
            "verification: our stored values disagree with IBKR beyond tolerance. See the "
            "Verification section (or `verification/ibkr` rows); re-run `algotrade-ingest verify "
            "--date D --symbols X` after fixing the producing task.",
        ),
        (
            r"^coverage_earnings\.last_earnings_date",
            "coverage_earnings.last_earnings_date (overdue earnings): a company's last report is "
            "over [quality.coverage.earnings.last_earnings_date] max_age_days old and it has no "
            "next date: the earnings calendar (Nasdaq) has dropped this company; check the "
            "source (re-running `earnings` will not add it). The Coverage section lists each "
            "name with its last report date.",
        ),
        (
            r"^coverage(?!_earnings\.last_earnings_date)",
            "coverage_<feature>: too few of the names the feature applies to have a value "
            "(under [quality.coverage.*] core_min / rest_min), or the share fell more than "
            "max_drop since the session before. See the Coverage section for the missing names; "
            "re-run the producing task (iv30: `chains` then `rollups`; earnings: `earnings`; "
            "price_stats: `bars`) for the session. Only a FAIL level holds the screens back.",
        ),
        (
            r"^bars_fresh|^bars_count",
            "Bars check failed: re-run `algotrade-ingest bars --date D` "
            "and check the Massive key and plan.",
        ),
    )
)


def hints(report: Report) -> tuple[str, ...]:
    """The hints whose pattern matches a failure reason, step error or failed check."""
    texts = [g.reason for g in report.failures]
    texts += [s.note for s in report.steps if s.status in BAD_STEPS]
    texts += [f"{c.name}: {c.detail}" for c in report.checks]
    texts += [reason for screen in report.screens for reason, _ in screen.gaps]
    texts += [v.note for v in report.verification if v.note]
    return tuple(h for pattern, h in HINTS if any(pattern.search(t) for t in texts))


def build_report(
    summary: Mapping[str, Any],
    records: Mapping[tuple[str, str], RunRecord],
    labels: Mapping[str, str] | None = None,
    max_examples: int = 5,
    history: Sequence[Mapping[str, float]] = (),
    max_duration_s: float | None = None,
    arrivals: Sequence[ArrivalStat] = (),
) -> Report:
    """The report for one nightly run. ``records``: (session, step) -> that step's task run
    record (``""`` session for the steps after every session); ``labels``: id -> ticker;
    ``history``: step -> seconds of earlier nightlies, newest first (the timing trend)."""
    labels = labels or {}
    lines, failures, checks, screens, rollups = [], [], [], [], []
    verification: list[VerificationLine] = []
    coverage: list[CoverageLine] = []
    for session, name, step in _steps(summary):
        record = records.get((session, name))
        result = step.get("result")
        note = str(step.get("error") or step.get("reason") or "")
        lines.append(
            StepLine(
                session,
                name,
                str(step.get("status")),
                float(step.get("duration_s", 0.0)),
                _counts(name, result),
                _items(record, result),
                note,
            )
        )
        if record is not None and name != "quality":  # checks are listed with their detail
            failures += _groups(session, name, record, labels, max_examples)
        checks += _checks(session, step)  # acceptance checks on the step (ADR 0039)
        checks += _checks(session, result) if name == "quality" else []  # before ADR 0039
        screens += _screens(session, result) if name == "screens" else []
        rollups += _rollups(session, result) if name == "rollups" else []
        verification += _verification(session, step) if name == "verify" else []
        coverage += _coverage(session, step, max_examples)
    warnings = tuple(
        str(w.get("detail", w)) if isinstance(w, Mapping) else str(w)
        for w in summary.get("warnings", [])
    )
    report = Report(
        sessions=tuple(summary.get("sessions", [])),
        status=str(summary.get("status", "?")),
        started=_parse(summary.get("started_at")),
        finished=_parse(summary.get("finished_at")),
        duration_s=float(summary.get("duration_s", 0.0)),
        warnings=warnings,
        steps=tuple(lines),
        failures=tuple(failures),
        checks=tuple(checks),
        screens=tuple(screens),
        rollups=tuple(rollups),
        max_duration_s=max_duration_s,
        catch_up_held=tuple((summary.get("catch_up") or {}).get("held", [])),
        catch_up_waiting=tuple((summary.get("catch_up") or {}).get("waiting", [])),
        verification=tuple(verification),
        coverage=tuple(coverage),
    )
    items = {key: len(r.items) for key, r in records.items() if r.items}
    timings = step_timings(list(_steps(summary)), report.started, report.duration_s, items, history)
    pacing = tuple(
        line
        for (session, name), record in records.items()
        for line in vendor_pacing(session, name, record.stats.get("pacing"))
    )
    return replace(
        report, hints=hints(report), timings=timings, pacing=pacing, arrivals=tuple(arrivals)
    )
