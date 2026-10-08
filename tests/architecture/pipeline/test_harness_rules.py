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
        r"^check:.*\n\tscripts/ops/check_lock\.sh \$\(MAKE\) .*check-gates$", makefile, re.M
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
