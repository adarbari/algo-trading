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
    assert re.search(
        r"^check:\n\tscripts/ops/check_lock\.sh \$\(MAKE\) check-gates$", makefile, re.M
    )
    gates = re.search(r"^check-gates:(.*)$", makefile, re.M)
    assert gates and {"lint", "test", "web-check", "web-real"} <= set(gates.group(1).split())
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


def test_only_the_label_setter_removes_the_label() -> None:
    for parts in (("CLAUDE.md",), (".claude", "agents", "implementer.md")):
        text = _flat(*parts)
        assert "Only the session that set `no-automerge` or `needs-owner` removes it" in text
        assert "an agent never removes a label it did not set" in text, parts
