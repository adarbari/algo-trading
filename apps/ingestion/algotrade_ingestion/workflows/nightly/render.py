"""Render a nightly ``Report`` (``report.py``) as plain text and as simple, self-contained HTML.

The HTML uses inline styles only (no images, scripts or external assets) so mail clients show
it as is. Times are shown in America/Los_Angeles (the owner's zone) and UTC. Both renderings
hold the same sections: header, statistics per step, run timing (start / end / share /
throughput / trend per step, slowest highlighted, sub-steps), failure deep
dive (step errors, failed items grouped by reason with examples, quality checks, screen
coverage gaps), rollups, verification vs IBKR (checks by status, failing examples), and what
to do.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from algotrade_ingestion.workflows.nightly.report import (
    BAD_STEPS,
    Example,
    Report,
    VerificationLine,
)
from algotrade_ingestion.workflows.nightly.timing import StepTiming

LOCAL = ZoneInfo("America/Los_Angeles")  # the owner's time zone for the email

WIDTH = 100


def _num(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {secs:02d}s"


def _when(value: datetime | None) -> str:
    """Local (America/Los_Angeles) and UTC: ``2026-10-03 06:26 PDT (13:26 UTC)``."""
    if value is None:
        return "-"
    local = value.astimezone(LOCAL)
    return f"{local:%Y-%m-%d %H:%M %Z} ({value.astimezone(UTC):%H:%M} UTC)"


def _clock(value: datetime | None) -> str:
    return f"{value.astimezone(LOCAL):%H:%M:%S}" if value else "-"


# ----------------------------------------------------------------------------- run timing

TIMING_HEAD = ["Step", "Start", "End", "Time", "Share", "Status", "Items", "Per min", "Prev",
               "Median", "Trend"]  # fmt: skip


def _slowest(report: Report) -> int | None:
    if not report.timings:
        return None
    return max(range(len(report.timings)), key=lambda i: report.timings[i].duration_s)


def _trend(t: StepTiming) -> str:
    base = t.median_s if t.median_s is not None else t.previous_s
    if base is None:
        return "-"
    if base <= 0:
        return "-"
    change = t.duration_s / base - 1
    return f"{change:+.0%}" + (" SLOWER" if t.slower else "")


def _timing_rows(report: Report) -> list[list[str]]:
    multi = len(report.sessions) > 1
    rows = []
    for t in report.timings:
        name = f"{t.session} {t.step}" if multi and t.session else t.step
        rows.append(
            [
                name,
                _clock(t.start),
                _clock(t.end),
                duration(t.duration_s),
                f"{t.share:.0%}",
                t.status,
                f"{t.items:,} {t.unit}" if t.items is not None else "-",
                f"{t.per_min:,.0f}" if t.per_min is not None else "-",
                duration(t.previous_s) if t.previous_s is not None else "-",
                duration(t.median_s) if t.median_s is not None else "-",
                _trend(t),
            ]
        )
    return rows


def _timing_overall(report: Report) -> list[tuple[str, str]]:
    total = duration(report.duration_s)
    if report.max_duration_s:
        over = report.duration_s > report.max_duration_s
        state = "OVER the alert threshold" if over else "within the alert threshold"
        total += f" ({state} of {duration(report.max_duration_s)})"
    sessions = ", ".join(report.sessions) or "none"
    if len(report.sessions) > 1:
        sessions += f" (catch-up: {len(report.sessions)} sessions)"
    if report.catch_up_dropped:
        sessions += f"; dropped over the cap: {', '.join(report.catch_up_dropped)}"
    slower = [t.step for t in report.timings if t.slower]
    rows = [
        ("Total", total),
        ("Sessions", sessions),
        ("Lock wait", "not recorded (the run lock is taken before the job starts)"),
    ]
    if slower:
        rows.append(("Slower than usual", ", ".join(slower) + " (>50% above the 7-run median)"))
    return rows


def _substeps(report: Report) -> list[str]:
    return [
        f"{t.step}: " + ", ".join(f"{name} {duration(s)}" for name, s in t.substeps)
        for t in report.timings
        if t.substeps
    ]


def _pacing(report: Report) -> list[str]:
    """One line per vendor limiter and step: requests, 429s, time waited, interval range."""
    multi = len(report.sessions) > 1
    out = []
    for p in report.pacing:
        name = f"{p.session} {p.step}" if multi and p.session else p.step
        text = (
            f"{name} / {p.key}: {p.requests:,} requests, {p.throttled_429} x 429 "
            f"(Retry-After {duration(p.retry_after_wait_s)}), "
            f"rate-limit wait {duration(p.limiter_wait_s)}"
        )
        if p.error_rate_slowdowns:
            text += f", {p.error_rate_slowdowns} error-rate slowdown(s)"
        if p.interval_min_s is not None and p.interval_max_s is not None:
            text += f", interval {p.interval_min_s:g}-{p.interval_max_s:g}s"
            if p.interval_final_s is not None:
                text += f" (final {p.interval_final_s:g}s)"
        out.append(text)
    return out


def _pairs(pairs: Iterable[tuple[str, Any]]) -> str:
    return ", ".join(f"{k} {_num(v)}" for k, v in pairs)


def _example(e: Example) -> str:
    symbol_id = e.label is not None and e.key.partition(":")[2] == e.label  # EQ:<SYMBOL>
    who = f"{e.label} ({e.key})" if e.label and not symbol_id else e.key
    return f"{who}: {e.message}"


def _header(report: Report) -> list[tuple[str, str]]:
    rows = [
        ("Sessions", ", ".join(report.sessions) or "none"),
        ("Status", report.status),
        ("Started", _when(report.started)),
        ("Finished", _when(report.finished)),
        ("Duration", duration(report.duration_s)),
        ("Steps with failures", str(len(report.bad_steps))),
    ]
    return rows + [("Warning", w) for w in report.warnings]


def _step_rows(report: Report) -> list[list[str]]:
    multi = len(report.sessions) > 1
    rows = []
    for s in report.steps:
        name = f"{s.session} {s.step}" if multi and s.session else s.step
        detail = _pairs(s.counts)
        if s.note:
            detail = f"{detail}; {s.note}" if detail else s.note
        rows.append([name, s.status, duration(s.duration_s), _pairs(s.items), detail])
    return rows


STEP_HEAD = ["Step", "Status", "Time", "Items", "Key counts"]


def _lines(texts: Iterable[str]) -> str:
    return "\n".join(texts)


def _verification_summary(v: VerificationLine) -> str:
    if v.note and not v.counts:
        return f"{v.status}: {v.note}"
    counts = _pairs(v.counts) or "no checks"
    return f"{v.status}: {v.instruments} instruments; {counts}"


# ----------------------------------------------------------------------------- text


def _table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    widths = [min(max(len(r[i]) for r in [head, *rows]), 60) for i in range(len(head) - 1)]

    def line(cells: Sequence[str]) -> str:
        fixed = [c.ljust(w) for c, w in zip(cells[:-1], widths, strict=True)]
        return "  ".join([*fixed, cells[-1]]).rstrip()

    return [line(head), line(["-" * w for w in widths] + ["-" * 10]), *map(line, rows)]


def render_text(report: Report) -> str:
    out = [report.subject(), "=" * min(WIDTH, len(report.subject())), ""]
    out += [f"{k + ':':<21}{v}" for k, v in _header(report)]
    out += ["", "STATISTICS", "", *_table(STEP_HEAD, _step_rows(report))]
    out += _text_timing(report)
    if report.screens:
        out += ["", "Screens"]
        for sc in report.screens:
            cov = f"{sc.coverage_pct:.1%}" if sc.coverage_pct is not None else "-"
            out.append(f"  {sc.config} ({sc.status}, coverage {cov}): {_pairs(sc.decisions)}")
    if report.rollups:
        out += ["", "Rollups (rows written)"]
        for _, name, rows, no_input in report.rollups:
            gap = f", no input for {no_input} session(s)" if no_input else ""
            out.append(f"  {name:<22}{rows:>12,}{gap}")
    if report.verification:
        out += ["", "VERIFICATION VS IBKR", ""]
        for v in report.verification:
            out.append(f"  {v.session}: {_verification_summary(v)}")
            out += [f"      {e}" for e in v.examples]
    out += ["", "FAILURE DEEP DIVE", ""]
    out += _text_failures(report)
    if report.hints:
        out += ["", "WHAT TO DO", ""] + [f"- {h}" for h in report.hints]
    return "\n".join(out) + "\n"


def _text_timing(report: Report) -> list[str]:
    if not report.timings:
        return []
    out = ["", "RUN TIMING (times America/Los_Angeles)", ""]
    out += [f"{k + ':':<21}{v}" for k, v in _timing_overall(report)]
    rows = _timing_rows(report)
    slowest = _slowest(report)
    if slowest is not None:
        rows[slowest][0] = f"*{rows[slowest][0]}"
    out += ["", *_table(TIMING_HEAD, rows), "  (* slowest step)"]
    subs = _substeps(report)
    if subs:
        out += ["", "Sub-steps", *(f"  {s}" for s in subs)]
    pacing = _pacing(report)
    if pacing:
        out += ["", "Vendor pacing", *(f"  {s}" for s in pacing)]
    return out


def _text_failures(report: Report) -> list[str]:
    out: list[str] = []
    errors = [s for s in report.bad_steps if s.note]
    if errors:
        out.append("Step errors")
        out += [f"  {s.step} {s.status}: {s.note}" for s in errors]
        out.append("")
    if report.failures:
        out.append("Failed items by reason")
        for g in report.failures:
            out.append(f"  [{g.step}] {g.reason}: {g.count:,}")
            out += [f"      {_example(e)}" for e in g.examples]
            if g.count > len(g.examples):
                out.append(f"      ... and {g.count - len(g.examples):,} more")
        out.append("")
    if report.checks:
        out.append("Quality checks not passing")
        out += [f"  {c.status} {c.name}: {c.detail}" for c in report.checks]
        out.append("")
    gaps = [(sc, r, n) for sc in report.screens for r, n in sc.gaps]
    if gaps:
        out.append("Screen coverage gaps (UNKNOWN by reason)")
        out += [f"  {sc.config}: {r}: {n:,}" for sc, r, n in gaps]
        out.append("")
    screen_errors = [f"  {sc.config}: {sc.error}" for sc in report.screens if sc.error]
    out += ["Screen errors", *screen_errors] if screen_errors else []
    while out and not out[-1]:
        out.pop()
    return out or ["No failures."]


# ----------------------------------------------------------------------------- HTML

_CSS_TABLE = "border-collapse:collapse;font-size:13px;margin:4px 0 16px 0"
_CSS_CELL = "border:1px solid #d0d7de;padding:4px 8px;text-align:left;vertical-align:top"
_CSS_HEAD = _CSS_CELL + ";background:#f6f8fa"
_STATUS_COLOR = {
    "COMPLETE": "#1a7f37",
    "PASS": "#1a7f37",
    "PARTIAL": "#9a6700",
    "WARN": "#9a6700",
    "BLOCKED": "#9a6700",
    "FAILED": "#cf222e",
    "FAIL": "#cf222e",
    "SKIPPED": "#57606a",
}


def _status(text: str) -> str:
    color = _STATUS_COLOR.get(text.upper(), "#24292f")
    return f'<b style="color:{color}">{escape(text)}</b>'


def _html_table(
    head: Sequence[str],
    rows: Sequence[Sequence[str]],
    status_col: int = -1,
    highlight: int | None = None,
) -> str:
    th = "".join(f'<th style="{_CSS_HEAD}">{escape(h)}</th>' for h in head)
    body = []
    for n, row in enumerate(rows):
        cells = [
            _status(c) if i == status_col else escape(c).replace("\n", "<br>")
            for i, c in enumerate(row)
        ]
        css = _CSS_CELL + (";background:#fff8c5;font-weight:600" if n == highlight else "")
        body.append("<tr>" + "".join(f'<td style="{css}">{c}</td>' for c in cells) + "</tr>")
    return f'<table style="{_CSS_TABLE}"><tr>{th}</tr>{"".join(body)}</table>'


def render_html(report: Report) -> str:
    h2 = '<h2 style="font-size:16px;margin:20px 0 6px 0">{}</h2>'
    h3 = '<h3 style="font-size:14px;margin:12px 0 4px 0">{}</h3>'
    parts = [
        f'<h1 style="font-size:18px;margin:0 0 8px 0">{escape(report.subject())}</h1>',
        _html_table(["", ""], [[k, v] for k, v in _header(report)]),
        h2.format("Statistics"),
        _html_table(STEP_HEAD, _step_rows(report), status_col=1),
    ]
    if report.timings:
        parts += [
            h2.format("Run timing (America/Los_Angeles)"),
            _html_table(["", ""], [[k, v] for k, v in _timing_overall(report)]),
            _html_table(TIMING_HEAD, _timing_rows(report), 5, _slowest(report)),
        ]
        for title, lines in (("Sub-steps", _substeps(report)), ("Vendor pacing", _pacing(report))):
            if lines:
                items = "".join(f"<li>{escape(s)}</li>" for s in lines)
                parts.append(h3.format(title))
                parts.append(f'<ul style="font-size:13px;margin:0 0 12px 0">{items}</ul>')
    if report.screens:
        rows = [
            [
                sc.config,
                sc.status.upper(),
                f"{sc.coverage_pct:.1%}" if sc.coverage_pct is not None else "-",
                _pairs(sc.decisions),
            ]
            for sc in report.screens
        ]
        parts += [
            h3.format("Screens"),
            _html_table(["Screen", "Status", "Coverage", "Decisions"], rows, status_col=1),
        ]
    if report.rollups:
        rows = [[n, _num(r), _num(g)] for _, n, r, g in report.rollups]
        parts += [h3.format("Rollups"), _html_table(["Rollup", "Rows", "No-input sessions"], rows)]
    if report.verification:
        rows = [
            [v.session, v.status, _verification_summary(v).split(": ", 1)[-1], _lines(v.examples)]
            for v in report.verification
        ]
        parts += [
            h2.format("Verification vs IBKR"),
            _html_table(["Session", "Status", "Checks", "Failing examples"], rows, status_col=1),
        ]
    parts.append(h2.format("Failure deep dive"))
    parts += _html_failures(report, h3)
    if report.hints:
        items = "".join(f"<li>{escape(h)}</li>" for h in report.hints)
        parts += [h2.format("What to do"), f'<ul style="font-size:13px">{items}</ul>']
    body = "".join(parts)
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head>'
        '<body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        f'color:#24292f;max-width:1000px">{body}</body></html>'
    )


def _html_failures(report: Report, h3: str) -> list[str]:
    parts: list[str] = []
    errors = [s for s in report.steps if s.status in BAD_STEPS and s.note]
    if errors:
        rows = [[s.step, s.status, s.note] for s in errors]
        parts += [h3.format("Step errors"), _html_table(["Step", "Status", "Error"], rows, 1)]
    if report.failures:
        rows = []
        for g in report.failures:
            examples = "\n".join(_example(e) for e in g.examples)
            if g.count > len(g.examples):
                examples += f"\n... and {g.count - len(g.examples):,} more"
            rows.append([g.step, g.reason, _num(g.count), examples])
        parts += [
            h3.format("Failed items by reason"),
            _html_table(["Step", "Reason", "Count", "Examples"], rows),
        ]
    if report.checks:
        rows = [[c.name, c.status, c.detail] for c in report.checks]
        parts += [
            h3.format("Quality checks not passing"),
            _html_table(["Check", "Status", "Detail"], rows, 1),
        ]
    gaps = [[sc.config, r, _num(n)] for sc in report.screens for r, n in sc.gaps]
    if gaps:
        parts += [
            h3.format("Screen coverage gaps (UNKNOWN by reason)"),
            _html_table(["Screen", "Reason", "Count"], gaps),
        ]
    errs = [[sc.config, sc.error] for sc in report.screens if sc.error]
    if errs:
        parts += [h3.format("Screen errors"), _html_table(["Screen", "Error"], errs)]
    return parts or ['<p style="font-size:13px">No failures.</p>']
