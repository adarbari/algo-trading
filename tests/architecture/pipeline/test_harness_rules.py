"""The harness rules that keep sessions from hurting each other on the one shared machine
(docs/ci.md "Pipeline"): CLAUDE.md forbids the broad `pkill`s, `make check` takes the lock,
and every web server port reads the per-worktree `ALGOTRADE_PORT_BASE`."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "apps" / "web"


def test_claude_md_forbids_the_broad_pkills() -> None:
    text = " ".join((REPO / "CLAUDE.md").read_text().split())
    for target in ("make", "node", "vite", "playwright"):
        assert f"`pkill -f {target}`" in text, f"CLAUDE.md must forbid pkill -f {target}"
    assert "kills another session's" in text and "by its PID" in text


def test_make_check_runs_the_gates_under_the_lock() -> None:
    makefile = (REPO / "Makefile").read_text()
    check = re.search(r"^check:.*?(?=^\S)", makefile, re.S | re.M)
    assert check and re.search(
        r"^\tscripts/ops/check_lock\.sh \$\(MAKE\) .*check-gates$", check.group(0), re.M
    )
    gates = re.search(r"^check-gates:(.*)$", makefile, re.M)
    assert gates and "$(CHECK_TARGETS)" in gates.group(1)  # scope-aware: docs/ci.md
    for var, members in (("CHECK_PY", {"lint", "test"}), ("CHECK_WEB", {"web-check", "web-real"})):
        line = re.search(rf"^{var} = (.*)$", makefile, re.M)
        assert line and members <= set(line.group(1).split()), var
    assert (REPO / "scripts" / "ops" / "check_lock.sh").stat().st_mode & 0o111


def test_web_servers_read_the_worktree_port_base() -> None:
    for name in ("vite.config.ts", "playwright.config.ts", "playwright.visual.config.ts",
                 "playwright.real.config.ts"):  # fmt: skip
        assert "ALGOTRADE_PORT_BASE" in (WEB / name).read_text(), name
    script = (REPO / "scripts" / "worktree.sh").read_text()
    assert "ALGOTRADE_PORT_BASE=" in script  # worktree.env sets it


def _flat(*parts: str) -> str:
    return " ".join(REPO.joinpath(*parts).read_text().split())


def test_needs_owner_label_is_in_the_rules_and_in_start() -> None:
    assert "`needs-owner`" in _flat("CLAUDE.md")
    assert "`needs-owner`" in _flat(".claude", "commands", "start.md")


def test_agent_briefs_demand_foreground_checks_and_a_last_action_hand_back() -> None:
    for name in ("implementer", "checker"):
        text = _flat(".claude", "agents", f"{name}.md")
        assert "foreground" in text, f"{name}.md must say checks run in the foreground"
        assert "no command may still be running" in text, name


def test_only_the_orchestrator_releases_no_automerge() -> None:
    claude = _flat("CLAUDE.md")
    assert "Only the session that set `no-automerge` removes it" in claude
    assert "`needs-owner` is never removed by an agent" in claude
    implementer = _flat(".claude", "agents", "implementer.md")
    assert "Only the orchestrating session removes `no-automerge`" in implementer
    assert "never removes `needs-owner`" in implementer


def _log_entries() -> list[str]:
    entries = REPO.joinpath("docs", "decisions", "log.md").read_text().split("\n## ")[1:]
    assert entries
    return entries


def test_decision_log_entries_have_date_status_and_decider() -> None:
    for entry in _log_entries():
        assert re.match(r"\d{4}-\d{2}-\d{2} \| ", entry), entry[:60]
        assert re.search(
            r"^- decided by: (owner( \(confirmed \d{4}-\d{2}-\d{2}\))?"
            r"|Fable on the owner's behalf|orchestrator \(design call\)"
            r"|proposed by orchestrator; awaiting owner)$",
            entry,
            re.M,
        ), entry[:60]
        assert re.search(
            r"^- status: (final|pending owner confirmation|overruled)$", entry, re.M
        ), entry[:60]


def test_only_the_owner_makes_a_log_entry_final() -> None:
    """`final` needs `decided by: owner...` or a `- confirmed: owner YYYY-MM-DD` line."""
    for entry in _log_entries():
        if re.search(r"^- status: final$", entry, re.M):
            assert re.search(r"^- decided by: owner\b", entry, re.M) or re.search(
                r"^- confirmed: owner \d{4}-\d{2}-\d{2}$", entry, re.M
            ), f"only the owner makes an entry final: {entry[:60]}"


POLICY_WORDS = re.compile(
    r"retention|retain|erase|erasure|personal data|privacy|who sees|sees all|visib|ADR \d{4}",
    re.I,
)


def test_the_orchestrator_does_not_decide_policy_topics() -> None:
    """Heuristic (the topic is free text): an `orchestrator (design call)` entry whose heading or
    question names a policy word (retention, personal data, who sees, an ADR...) is rejected."""
    for entry in _log_entries():
        if "- decided by: orchestrator" in entry:
            head = entry.split("\n- Decision:")[0]
            assert not POLICY_WORDS.search(head), f"policy goes to the owner: {entry[:60]}"


def test_one_policy_list_in_the_skill_is_cited_by_the_agents() -> None:
    skill = _flat(".claude", "skills", "review-and-release", "SKILL.md")
    assert "Owner only" in skill and "no `needs-owner` label" in skill
    for name in ("architect", "implementer"):
        assert "review-and-release" in _flat(".claude", "agents", f"{name}.md"), name
    assert "docs/decisions/log.md" in _flat(".claude", "commands", "start.md")


def test_auto_merge_skips_needs_owner_like_no_automerge() -> None:
    script = REPO.joinpath("scripts", "auto_merge.sh").read_text()
    assert '"no-automerge"' in script and '"needs-owner"' in script


def test_claude_md_names_the_four_model_tiers() -> None:
    text = _flat("CLAUDE.md")
    section = text[text.index("## Agents, models and tokens") :]
    for tier in ("Haiku = `checker`", "Sonnet = `implementer`", "Opus = `architect`",
                 "orchestrating session"):  # fmt: skip
        assert tier in section, f"CLAUDE.md must name the tier: {tier}"


def test_append_only_logs_merge_by_union() -> None:
    # parallel PRs each append a row; without this every pair conflicted (2026-10 edge build)
    attrs = (REPO / ".gitattributes").read_text().split("\n")
    for log in ("docs/decisions/log.md", "docs/history.md"):
        assert f"{log} merge=union" in attrs, log


def test_the_release_skill_names_the_auto_merge_nudge() -> None:
    skill = (REPO / ".claude/skills/review-and-release/SKILL.md").read_text()
    assert "gh workflow run auto-merge.yml" in skill
    assert "workflow_dispatch" in (REPO / ".github/workflows/auto-merge.yml").read_text()
