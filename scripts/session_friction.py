"""`make friction`: what slowed the last sessions down, from their transcripts. Read-only.

Scans every Claude Code transcript of this repo (`~/.claude/projects/<repo slug>/*.jsonl` and
the subagent transcripts under `<session>/subagents/`) since a date and counts the friction
signals a harness rule, check or script could remove: blocked and failing tool calls
(clustered by message), gate runs against gate failures (`make check`, `make changed`,
pytest, vitest, ...), the same failing command retried, permission denials, hook errors
and the owner's corrections, plus the token spend per model tier (the last usage snapshot
of each transcript) and which work-item sessions ran on the expensive tiers. Ranks the
frictions by count x sessions touched, prints the top ones and writes the full report
(markdown + JSON) under `var/harness/friction/`. It never reads
the store and never judges: `.claude/skills/review-sessions` reads the report and decides.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "var" / "harness" / "friction"
GATES = (
    "make check",
    "make changed",
    "make web-check",
    "make arch",
    "make layout",
    "make ownership",
    "make dupes",
    "make filelen",
    "pytest",
    "vitest",
    "playwright",
    "eslint",
    "npm run",
    "git push",
    "git merge",
    "gh pr create",
    "worktree.sh",
)
FAIL_RE = re.compile(r"^Exit code [1-9]|\bFAILED\b|\berror(s)?:|\bError\b|ENOSPC", re.M)
CORRECTION_RE = re.compile(
    r"\b(no[,.]|don't|do not|never|stop|wrong|instead|why did|not what)\b", re.I
)
EXCERPT = 110
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
EXPENSIVE = ("fable", "opus")


def _tier(model: str) -> str:
    """`claude-opus-5-5` -> `opus`; the tier is what the routing rule talks about."""
    parts = model.split("-")
    return parts[1] if len(parts) > 1 and parts[0] == "claude" else model


@dataclass
class Signal:
    """One ranked row of the report: what, how often, in how many sessions, one example."""

    kind: str
    key: str
    count: int = 0
    sessions: set[str] = field(default_factory=set)
    example: str = ""

    @property
    def score(self) -> int:
        return self.count * len(self.sessions)

    def row(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "key": self.key,
            "count": self.count,
            "sessions": sorted(self.sessions),
            "score": self.score,
            "example": self.example,
        }


@dataclass
class Session:
    """One transcript: a main session or a subagent, with the PRs it linked."""

    agent: bool
    turns: int = 0
    prs: set[int] = field(default_factory=set)
    start: str = ""
    end: str = ""
    title: str = ""
    cost: dict[str, float] = field(default_factory=dict)
    edits: Counter[str] = field(default_factory=Counter)

    @property
    def total_cost(self) -> float:
        return sum(self.cost.values())

    def row(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "turns": self.turns,
            "prs": sorted(self.prs),
            "start": self.start,
            "end": self.end,
            "title": self.title,
            "cost": self.cost,
            "edits": dict(self.edits),
        }


@dataclass
class Report:
    since: date
    files: int = 0
    sessions: dict[str, Session] = field(default_factory=dict)
    signals: dict[tuple[str, str], Signal] = field(default_factory=dict)
    gate_runs: Counter[str] = field(default_factory=Counter)
    gate_fails: Counter[str] = field(default_factory=Counter)
    corrections: list[tuple[str, str]] = field(default_factory=list)

    def note(self, kind: str, key: str, session: str, example: str = "") -> None:
        sig = self.signals.setdefault((kind, key), Signal(kind, key))
        sig.count += 1
        sig.sessions.add(session)
        sig.example = sig.example or example[:EXCERPT]

    def ranked(self) -> list[Signal]:
        return sorted(self.signals.values(), key=lambda s: (-s.score, -s.count, s.key))

    def prs(self) -> set[int]:
        return {pr for s in self.sessions.values() for pr in s.prs}


def main_checkout(repo: Path = REPO) -> Path:
    """The main checkout (a worktree's transcripts live under the main checkout's slug)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return repo
    return Path(out.stdout.strip()).parent if out.returncode == 0 and out.stdout.strip() else repo


def project_dir(repo: Path = REPO) -> Path:
    """Claude Code keeps a repo's transcripts under ~/.claude/projects/<path with / as ->."""
    slug = str(main_checkout(repo).resolve()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug


def transcripts(projects: Path) -> list[Path]:
    return sorted(projects.glob("*.jsonl")) + sorted(projects.glob("*/subagents/*.jsonl"))


def _normalise(text: str) -> str:
    """A cluster key: the first line (two for a bare exit code), paths and numbers masked."""
    text = text.replace("<tool_use_error>", "").replace("</tool_use_error>", "")
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    keep = 2 if lines and lines[0].startswith("Exit code") else 1
    text = " ".join(lines[:keep])
    text = re.sub(r"/[\w./-]+", "<path>", text)
    return re.sub(r"\d+", "N", text)[:90]


def _failure_line(text: str) -> str:
    """The line that says what failed (a FAILED test, an error), not the shell's trailer."""
    for ln in text.splitlines():
        if FAIL_RE.search(ln) and not ln.startswith("Exit code"):
            return ln.strip()
    return next((ln for ln in text.splitlines() if ln.strip()), "")


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _gate(cmd: str) -> str | None:
    return next((g for g in GATES if g in cmd), None)


def _is_correction(rec: dict[str, object], content: object) -> str | None:
    """The owner's text when it reads like a correction; never a tool result or a meta note."""
    if rec.get("isMeta") or isinstance(content, list):
        return None
    text = _text(content)
    if len(text) < 400 and not text.startswith("[") and CORRECTION_RE.search(text):
        return text[:160].replace("\n", " ")
    return None


def _scan_file(path: Path, report: Report, since: datetime) -> None:
    sid = path.stem[:8]
    is_agent = path.parent.name == "subagents"
    session = report.sessions.setdefault(sid, Session(agent=is_agent))
    pending: dict[str, tuple[str, str]] = {}
    failed_cmds: Counter[str] = Counter()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = str(rec.get("timestamp") or "")
            if ts and datetime.fromisoformat(ts.replace("Z", "+00:00")) < since:
                continue
            _scan_record(rec, sid, session, report, pending, failed_cmds)
    for cmd, n in failed_cmds.items():
        if n >= 2:
            report.note("retried failing command", cmd[:EXCERPT], sid, cmd)


def _scan_meta(rec: dict[str, object], session: Session) -> None:
    """The record's bookkeeping: times, linked PRs, the title, the cumulative usage snapshot."""
    if ts := str(rec.get("timestamp") or ""):
        session.start = session.start or ts
        session.end = ts
    if rec.get("type") == "pr-link" and rec.get("prNumber"):
        session.prs.add(int(str(rec["prNumber"])))
    if rec.get("customTitle"):
        session.title = str(rec["customTitle"])
    if isinstance(usage := rec.get("modelUsage"), dict):  # cumulative: the last one wins
        session.cost = {
            _tier(m): float(u.get("costUSD") or 0) for m, u in usage.items() if isinstance(u, dict)
        }


def _scan_record(
    rec: dict[str, object],
    sid: str,
    session: Session,
    report: Report,
    pending: dict[str, tuple[str, str]],
    failed_cmds: Counter[str],
) -> None:
    kind = rec.get("type")
    _scan_meta(rec, session)
    if rec.get("toolDenialKind"):
        report.note("permission denial", str(rec["toolDenialKind"]), sid)
    if rec.get("hookErrors"):
        errors = str(rec["hookErrors"])
        report.note("hook error", _normalise(errors), sid, errors)
    message = rec.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if kind == "assistant":
        session.turns += 1
    if kind == "user" and not session.agent and (text := _is_correction(rec, content)):
        report.corrections.append((sid, text))
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            if block.get("name") in EDIT_TOOLS and isinstance(message, dict):
                session.edits[_tier(str(message.get("model") or "?"))] += 1
            inp = block.get("input") or {}
            cmd = str(inp.get("command", "")) if block.get("name") == "Bash" else ""
            pending[str(block.get("id"))] = (str(block.get("name")), cmd)
            if (gate := _gate(cmd)) is not None:
                report.gate_runs[gate] += 1
        elif block.get("type") == "tool_result":
            tool, cmd = pending.get(str(block.get("tool_use_id")), ("?", ""))
            _scan_result(block, tool, cmd, sid, report, failed_cmds)


def _scan_result(
    block: dict[str, object],
    tool: str,
    cmd: str,
    sid: str,
    report: Report,
    failed_cmds: Counter[str],
) -> None:
    text = _text(block.get("content"))
    if block.get("is_error"):
        if text.lstrip().startswith("<tool_use_error>Blocked"):
            report.note("blocked tool call", _normalise(text), sid, cmd or text)
        else:
            report.note(f"{tool} error", _normalise(text), sid, cmd or text)
    if tool == "Bash" and cmd and FAIL_RE.search(text):
        failed_cmds[cmd] += 1
        if (gate := _gate(cmd)) is not None:
            report.gate_fails[gate] += 1
            report.note("gate failure", gate, sid, _failure_line(text))


def scan(projects: Path, since: date) -> Report:
    report = Report(since=since)
    start = datetime.combine(since, datetime.min.time(), tzinfo=UTC)
    for path in transcripts(projects):
        report.files += 1
        _scan_file(path, report, start)
    report.sessions = {sid: s for sid, s in report.sessions.items() if s.turns or s.prs}
    return report


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def render(report: Report, top: int) -> str:
    """The markdown report: summary, gates, ranked signals, corrections, sessions."""
    main = [s for s in report.sessions.values() if not s.agent]
    agents = len(report.sessions) - len(main)
    checks = report.gate_runs["make check"]
    prs = report.prs()
    per_pr = f" ({checks / len(prs):.1f} per PR; the rule is one, before the push)" if prs else ""
    lines = [
        f"# Session friction since {report.since}",
        "",
        f"{len(main)} sessions, {agents} subagents, {len(prs)} PRs linked, "
        f"{report.files} transcripts read.",
        f"Full `make check` runs: {checks}{per_pr}",
        "",
        "## Gates: runs vs failures",
        "",
        "| Gate | Runs | Failures |",
        "|---|---|---|",
    ]
    for gate, runs in report.gate_runs.most_common():
        lines.append(f"| `{gate}` | {runs} | {report.gate_fails[gate]} |")
    lines += [
        "",
        f"## Top {top} signals (count x sessions)",
        "",
        "| # | Kind | What | Count | Sessions | Example |",
        "|---|---|---|---|---|---|",
    ]
    for i, sig in enumerate(report.ranked()[:top], 1):
        lines.append(
            f"| {i} | {sig.kind} | `{_cell(sig.key)}` | {sig.count} | {len(sig.sessions)} | "
            f"`{_cell(sig.example)}` |"
        )
    lines += spend_lines(report)
    lines += ["", "## Owner corrections (read them; the script does not judge)", ""]
    lines += [f"- `{sid}`: {text}" for sid, text in report.corrections] or ["- none found"]
    lines += [
        "",
        "## Sessions",
        "",
        "| Session | Kind | Start | End | Turns | PRs |",
        "|---|---|---|---|---|---|",
    ]
    for sid, s in sorted(report.sessions.items(), key=lambda kv: kv[1].start):
        kind = "agent" if s.agent else "session"
        prs_s = ", ".join(str(p) for p in sorted(s.prs))
        lines.append(f"| {sid} | {kind} | {s.start[:16]} | {s.end[:16]} | {s.turns} | {prs_s} |")
    return "\n".join(lines) + "\n"


def _cost_breakdown(session: Session) -> str:
    by_cost = sorted(session.cost.items(), key=lambda kv: -kv[1])
    return ", ".join(f"{tier} ${cost:,.0f}" for tier, cost in by_cost)


def spend_lines(report: Report) -> list[str]:
    """Token spend per tier, the costliest sessions, and implementation done on fable / opus."""
    per_tier: Counter[str] = Counter()
    for s in report.sessions.values():
        per_tier.update(s.cost)
    lines = ["", "## Token spend by model tier (last usage snapshot per transcript)", ""]
    lines += ["| Tier | Cost | Share |", "|---|---|---|"]
    total = sum(per_tier.values()) or 1.0
    for tier, cost in per_tier.most_common():
        lines.append(f"| {tier} | ${cost:,.2f} | {cost / total:.0%} |")
    lines.append(f"| all | ${total:,.2f} | |")
    main = sorted(
        (s for s in report.sessions.values() if not s.agent and s.cost),
        key=lambda s: -s.total_cost,
    )
    lines += ["", "| Session | Cost | Edits by tier | Title |", "|---|---|---|---|"]
    for s in main[:10]:
        edits = ", ".join(f"{t} {n}" for t, n in s.edits.most_common())
        lines.append(
            f"| {_cell(s.title) or '?'} | ${s.total_cost:,.2f} | {edits} | |".replace(
                f"| {_cell(s.title) or '?'} |", f"| {s.start[:10]} |", 1
            ).replace("| |", f"| {_cell(s.title)[:50]} |", 1)
        )
    flagged = [
        s for s in main if s.prs and sum(s.cost.get(t, 0.0) for t in EXPENSIVE) > 0.5 * s.total_cost
    ]
    lines += [
        "",
        "Work-item sessions (they opened PRs) orchestrated on the expensive tiers (over half the "
        'cost on fable / opus; CLAUDE.md "Agents, models and tokens": a work item runs from a '
        "Sonnet session, Opus and Fable are called for design and research):",
        "",
    ]
    lines += [
        f"- {s.start[:10]} {_cell(s.title)[:60]}: ${s.total_cost:,.2f} "
        f"({_cost_breakdown(s)}),"
        f" PRs {', '.join(str(p) for p in sorted(s.prs))}"
        for s in flagged
    ] or ["- none"]
    return lines


def write(report: Report, out: Path, top: int) -> tuple[Path, Path]:
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).date().isoformat()
    md, js = out / f"{stamp}.md", out / f"{stamp}.json"
    md.write_text(render(report, top), encoding="utf-8")
    payload = {
        "since": report.since.isoformat(),
        "files": report.files,
        "gate_runs": dict(report.gate_runs),
        "gate_fails": dict(report.gate_fails),
        "signals": [s.row() for s in report.ranked()],
        "corrections": report.corrections,
        "sessions": {sid: s.row() for sid, s in report.sessions.items()},
    }
    js.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return md, js


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    week_ago = datetime.now(tz=UTC).date() - timedelta(days=7)
    parser.add_argument("--since", type=date.fromisoformat, default=week_ago)
    parser.add_argument("--projects", type=Path, default=None, help="transcript folder")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args(argv)
    projects = args.projects or project_dir()
    if not projects.is_dir():
        print(f"no transcripts: {projects} does not exist", file=sys.stderr)
        return 1
    report = scan(projects, args.since)
    md, js = write(report, args.out, args.top)
    text = render(report, args.top)
    print(text[: text.index("## Owner corrections")].rstrip())
    print(f"\n{len(report.corrections)} owner corrections and the sessions: {md} (json: {js})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
