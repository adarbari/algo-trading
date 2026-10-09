"""`scripts/ops/deploy.sh`: the manual deploy and the launchd cycle (`--auto`, ADR 0057), run
against a temp git repo with stub tools on PATH (no network, no launchctl, no real build)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "deploy.sh"

API_STUB = """#!/bin/sh
echo "api $*" >> "$STUB_LOG"
case "$1" in
  deploy-plan)
    case " $* " in
      *" --locks "*) echo "${STUB_LOCKS-ingest}" ;;
      *) echo "${STUB_PLAN:-restart}" ;;
    esac ;;
  deploy-verify) exit "${STUB_VERIFY_RC:-0}" ;;
  schedule)
    while [ $# -gt 0 ]; do
      if [ "$1" = --out ]; then mkdir -p "$(dirname "$2")"; echo plist > "$2"; fi
      shift
    done ;;
esac
"""
INGEST_STUB = """#!/bin/sh
echo "ingest $*" >> "$STUB_LOG"
shift; [ "$1" = --deploy-only ] && shift; [ "$1" = -- ] && shift
if [ -n "$STUB_BUSY" ]; then exit 75; fi
exec "$@"
"""
MAKE_STUB = """#!/bin/sh
echo "make $*" >> "$STUB_LOG"
for a in "$@"; do
  case "$a" in
    WEB_DIST=*) d="${a#WEB_DIST=}"; mkdir -p "$d/assets"; echo new > "$d/index.html"
                echo new > "$d/assets/new.js" ;;
  esac
done
"""
LOGGING_STUB = '#!/bin/sh\necho "$(basename "$0") $*" >> "$STUB_LOG"\n'


def _git(cwd: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "PATH": os.environ["PATH"],
        "HOME": str(cwd),
    }
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "main"
    repo.mkdir()
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / ".gitignore").write_text("*.local.toml\nvar/\n")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "push", "-q", "origin", "main")
    return repo


def _advance(repo: Path, rel: str) -> str:
    """Another session lands a commit on origin/main; its sha."""
    clone = repo.parent / "other"
    if not clone.exists():
        _git(repo.parent, "clone", "-q", str(repo.parent / "origin.git"), str(clone))
    _git(clone, "pull", "-q", "origin", "main")
    (clone / rel).parent.mkdir(parents=True, exist_ok=True)
    (clone / rel).write_text(rel)
    _git(clone, "add", ".")
    _git(clone, "commit", "-qm", rel)
    _git(clone, "push", "-q", "origin", "main")
    return _git(clone, "rev-parse", "HEAD")


class Site:
    """A repo, a stub bin directory, and a way to run the script in them."""

    def __init__(self, tmp_path: Path) -> None:
        self.repo = _repo(tmp_path)
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.calls = tmp_path / "calls.log"
        self.calls.touch()
        for name, body in {
            "algotrade-api": API_STUB,
            "algotrade-ingest": INGEST_STUB,
            "make": MAKE_STUB,
            "notify": LOGGING_STUB,
        }.items():
            self._stub(name, body)
        for name in ("uv", "npm", "node", "curl", "launchctl"):
            self._stub(name, LOGGING_STUB)
        self.agents = tmp_path / "agents"
        self.agents.mkdir()
        self.env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "STUB_LOG": str(self.calls),
            "ALGOTRADE_DEPLOY_API": str(self.bin / "algotrade-api"),
            "ALGOTRADE_DEPLOY_INGEST": str(self.bin / "algotrade-ingest"),
            "ALGOTRADE_DEPLOY_NOTIFY": str(self.bin / "notify"),
            "ALGOTRADE_DEPLOY_AGENTS": str(self.agents),
        }

    def _stub(self, name: str, body: str) -> None:
        (self.bin / name).write_text(body)
        (self.bin / name).chmod(0o755)

    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def called(self) -> list[str]:
        return self.calls.read_text().splitlines()

    def notices(self) -> list[str]:
        return [c for c in self.called() if c.startswith("notify")]

    def state(self, name: str) -> Path:
        return self.repo / "var" / "deploy" / name

    def seed(self) -> str:
        sha = _git(self.repo, "rev-parse", "HEAD")
        self.state("last_sha").parent.mkdir(parents=True, exist_ok=True)
        self.state("last_sha").write_text(sha + "\n")
        return sha

    def log(self) -> str:
        path = self.repo / "var" / "logs" / "deploy.log"
        return path.read_text() if path.exists() else ""


@pytest.fixture
def site(tmp_path: Path) -> Site:
    return Site(tmp_path)


# ---- the manual deploy (unchanged guards) ---------------------------------------------------


def test_refuses_off_main(site: Site) -> None:
    _git(site.repo, "switch", "-qc", "feat/x")
    out = site.run("--dry-run")
    assert out.returncode == 1 and "not main" in out.stderr


def test_refuses_a_dirty_tree_but_not_the_ignored_overlay(site: Site) -> None:
    (site.repo / "llm.local.toml").write_text("enabled = true\n")  # git-ignored overlay
    assert site.run("--dry-run").returncode == 0
    (site.repo / "a.txt").write_text("changed\n")
    out = site.run("--dry-run")
    assert out.returncode == 1 and "uncommitted" in out.stderr


def test_refuses_unpushed_local_commits(site: Site) -> None:
    (site.repo / "b.txt").write_text("b\n")
    _git(site.repo, "add", ".")
    _git(site.repo, "commit", "-qm", "local only")
    out = site.run("--dry-run")
    assert out.returncode == 1 and "not on origin/main" in out.stderr


def test_dry_run_prints_the_whole_plan_and_runs_nothing(site: Site) -> None:
    out = site.run("--dry-run")
    assert out.returncode == 0, out.stderr
    plan = [x for x in out.stdout.splitlines() if x.startswith("[dry-run]")]
    heads = [x.split()[1] for x in plan]
    assert [Path(h).name for h in heads] == [
        "git", "uv", "make", "launchctl", "algotrade-api", "swap", "algotrade-api",
    ]  # fmt: skip
    assert "merge --ff-only" in plan[0] and "sync --all-packages --locked" in plan[1]
    assert "web-build" in plan[2] and "kickstart -k" in plan[3]
    assert "--check api" in plan[4] and "--check web" in plan[6]
    assert site.called() == [] and not site.state("last_sha").exists()


def test_a_manual_deploy_does_everything_and_records_the_commit(site: Site) -> None:
    sha = _advance(site.repo, "src/algotrade/x.py")
    out = site.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert site.called()[0].startswith("ingest deploy-hold -- bash ")  # through the locks
    assert any(c.startswith("uv sync --all-packages --locked") for c in site.called())
    assert site.state("last_sha").read_text().strip() == sha
    assert _git(site.repo, "rev-parse", "HEAD") == sha
    assert (site.repo / "var" / "web" / "index.html").read_text().strip() == "new"


def test_a_manual_deploy_that_works_clears_the_block(site: Site) -> None:
    site.state("blocked").parent.mkdir(parents=True)
    site.state("blocked").write_text("old reason\n")
    assert site.run().returncode == 0
    assert not site.state("blocked").exists()


def test_script_is_executable_and_bash_parses_it() -> None:
    assert os.access(SCRIPT, os.X_OK) and shutil.which("bash")
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0


# ---- the launchd cycle ----------------------------------------------------------------------


def test_blocked_exits_zero_without_fetching(site: Site) -> None:
    _git(site.repo, "remote", "set-url", "origin", "/nonexistent")  # a fetch would fail
    site.state("blocked").parent.mkdir(parents=True)
    site.state("blocked").write_text("x\n")
    out = site.run("--auto")
    assert (out.returncode, out.stdout, out.stderr) == (0, "", "")
    assert site.called() == [] and not site.state("fetch_failures").exists()


def test_nothing_moved_exits_at_once_and_logs_nothing(site: Site) -> None:
    site.seed()
    out = site.run("--auto")
    assert (out.returncode, out.stdout) == (0, "")
    assert site.called() == [] and site.log() == ""


def test_the_first_run_seeds_last_sha_from_head(site: Site) -> None:
    head = _git(site.repo, "rev-parse", "HEAD")
    assert site.run("--auto").returncode == 0
    assert site.state("last_sha").read_text().strip() == head
    assert "seeded last_sha" in site.log() and site.called() == []


def test_a_missing_tool_blocks(site: Site) -> None:
    (site.bin / "node").unlink()
    out = site.run("--auto", PATH=f"{site.bin}:/usr/bin:/bin")
    assert "node not found" in out.stderr and site.state("blocked").exists()


def test_a_manual_deploy_also_needs_its_tools(site: Site) -> None:
    (site.bin / "npm").unlink()
    out = site.run(PATH=f"{site.bin}:/usr/bin:/bin")
    assert out.returncode == 1 and "npm not found" in out.stderr and site.called() == []


def test_an_auto_dry_run_does_not_seed_or_block(site: Site) -> None:
    out = site.run("--auto", "--dry-run")
    assert out.returncode == 0, out.stderr
    assert not site.state("last_sha").exists() and site.log() == ""


def test_a_running_deploy_makes_auto_skip_instead_of_blocking_on_its_dirty_tree(site: Site) -> None:
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        site.state("applying").parent.mkdir(parents=True)
        site.state("applying").write_text(f"{sleeper.pid}\n")
        (site.repo / "a.txt").write_text("mid-merge\n")
        out = site.run("--auto")
        assert out.returncode == 0 and not site.state("blocked").exists()
        assert "skipped: deploy running" in site.log() and site.notices() == []
    finally:
        sleeper.kill()
        sleeper.wait()
    stale = site.run("--auto")  # the pid is gone: the marker no longer excuses the dirty tree
    assert stale.returncode == 1 and site.state("blocked").exists()


def test_the_applying_marker_is_removed_when_a_deploy_ends(site: Site) -> None:
    _advance(site.repo, "src/x.py")
    assert site.run().returncode == 0
    assert not site.state("applying").exists()


def test_a_dirty_tree_blocks_and_notifies_once(site: Site) -> None:
    (site.repo / "a.txt").write_text("changed\n")
    out = site.run("--auto")
    assert out.returncode == 1 and "uncommitted" in site.state("blocked").read_text()
    assert len(site.notices()) == 1 and "--clear" in site.notices()[0]
    again = site.run("--auto")
    assert again.returncode == 0 and len(site.notices()) == 1  # stopped until cleared


def test_a_diverged_main_blocks(site: Site) -> None:
    (site.repo / "b.txt").write_text("b\n")
    _git(site.repo, "add", ".")
    _git(site.repo, "commit", "-qm", "local only")
    assert site.run("--auto").returncode == 1
    assert "not on origin/main" in site.state("blocked").read_text()


def test_a_last_sha_off_main_blocks(site: Site) -> None:
    site.state("last_sha").parent.mkdir(parents=True)
    site.state("last_sha").write_text("0" * 40 + "\n")
    _advance(site.repo, "src/x.py")
    assert site.run("--auto").returncode == 1
    assert "not an ancestor" in site.state("blocked").read_text()


def test_twelve_failed_fetches_in_a_row_block(site: Site) -> None:
    site.seed()
    _git(site.repo, "remote", "set-url", "origin", "/nonexistent")
    site.state("fetch_failures").write_text("10\n")
    assert site.run("--auto").returncode == 0 and not site.state("blocked").exists()
    assert site.state("fetch_failures").read_text().strip() == "11"
    assert site.run("--auto").returncode == 1
    assert "fetch failed 12 times" in site.state("blocked").read_text()


def test_only_what_changed_is_deployed(site: Site) -> None:
    site.seed()
    sha = _advance(site.repo, "src/algotrade/x.py")
    out = site.run("--auto", STUB_PLAN="restart")
    assert out.returncode == 0, out.stdout + out.stderr
    calls = site.called()
    assert any(c.startswith("launchctl kickstart -k gui/") for c in calls)
    assert any(f"deploy-verify --expect {sha} --check full" in c for c in calls)
    assert not any(c.startswith(("make", "uv")) for c in calls)  # no web build, no sync
    assert site.state("last_sha").read_text().strip() == sha
    assert _git(site.repo, "rev-parse", "HEAD") == sha
    assert f"deployed {sha[:9]} (restart)" in site.log()


def test_a_web_change_is_built_aside_and_swapped_in_keeping_old_assets(site: Site) -> None:
    site.seed()
    web = site.repo / "var" / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text('<script src="/assets/old.js"></script>')
    (web / "assets" / "old.js").write_text("old")
    (web / "assets" / "ancient.js").write_text("older generation")
    sha = _advance(site.repo, "apps/web/src/a.ts")
    out = site.run("--auto", STUB_PLAN="web")
    assert out.returncode == 0, out.stdout + out.stderr
    assert (web / "index.html").read_text().strip() == "new"
    assert (web / "assets" / "new.js").exists() and (web / "assets" / "old.js").exists()
    assert not (web / "assets" / "ancient.js").exists()  # only the previous build's own files
    assert "old.js" in (site.repo / "var" / "deploy" / "web.prev" / "index.html").read_text()
    calls = site.called()
    assert any("make web-build WEB_DIST=var/deploy/web.next" in c for c in calls)
    assert any(f"deploy-verify --expect {sha} --check web" in c for c in calls)
    assert not any(c.startswith("launchctl") for c in calls)


def test_a_web_and_api_change_checks_the_api_before_and_the_web_after_the_swap(site: Site) -> None:
    site.seed()
    _advance(site.repo, "apps/api/schema.graphql")
    assert site.run("--auto", STUB_PLAN="web restart").returncode == 0
    checks = [c.rsplit(" ", 1)[1] for c in site.called() if "deploy-verify" in c]
    assert checks == ["api", "web"]


def test_busy_skips_without_touching_anything(site: Site) -> None:
    before = site.seed()
    _advance(site.repo, "src/x.py")
    out = site.run("--auto", STUB_BUSY="1")
    assert out.returncode == 0
    assert "skipped: ingest/deploy running" in site.log()
    assert site.state("last_sha").read_text().strip() == before
    assert not site.state("blocked").exists() and site.notices() == []
    assert _git(site.repo, "rev-parse", "HEAD") == before


def test_a_web_only_plan_holds_the_deploy_lock_alone(site: Site) -> None:
    site.seed()
    _advance(site.repo, "apps/web/src/a.ts")
    out = site.run("--auto", STUB_PLAN="web", STUB_LOCKS="")
    assert out.returncode == 0, out.stdout + out.stderr
    assert any(c.startswith("ingest deploy-hold --deploy-only -- bash ") for c in site.called())


def test_a_plan_that_touches_the_ingest_keeps_both_locks(site: Site) -> None:
    site.seed()
    _advance(site.repo, "src/algotrade/x.py")
    assert site.run("--auto", STUB_PLAN="restart").returncode == 0
    holds = [c for c in site.called() if c.startswith("ingest deploy-hold")]
    assert holds and all("--deploy-only" not in c for c in holds)


def test_a_deploy_only_skip_names_the_deploy_alone(site: Site) -> None:
    site.seed()
    _advance(site.repo, "apps/web/src/a.ts")
    assert site.run("--auto", STUB_PLAN="web", STUB_LOCKS="", STUB_BUSY="1").returncode == 0
    assert "skipped: deploy running" in site.log()
    assert "ingest/deploy" not in site.log()


def test_a_failed_locks_plan_blocks_and_runs_no_hold(site: Site) -> None:
    site._stub(
        "algotrade-api",
        API_STUB.replace('*" --locks "*) echo', '*" --locks "*) exit 1; echo'),
    )
    site.seed()
    _advance(site.repo, "apps/web/src/a.ts")
    out = site.run("--auto", STUB_PLAN="web")
    assert out.returncode == 1 and "deploy-plan failed" in site.state("blocked").read_text()
    assert not any(c.startswith("ingest") for c in site.called())


def test_the_dry_run_says_which_locks_it_would_take(site: Site) -> None:
    out = site.run("--dry-run")
    assert "locks (dry-run): deploy, ingest" in out.stdout


def test_a_failed_verify_blocks_notifies_and_keeps_last_sha(site: Site) -> None:
    before = site.seed()
    _advance(site.repo, "src/x.py")
    out = site.run("--auto", STUB_VERIFY_RC="1")
    assert out.returncode == 1
    assert "did not come back" in site.state("blocked").read_text()
    assert len(site.notices()) == 1
    assert site.state("last_sha").read_text().strip() == before  # no auto-rollback either
    assert site.run("--auto").returncode == 0 and len(site.notices()) == 1


def test_a_failed_web_build_blocks_before_anything_is_restarted_or_swapped(site: Site) -> None:
    site.seed()
    site._stub("make", "#!/bin/sh\nexit 2\n")
    web = site.repo / "var" / "web"
    web.mkdir(parents=True)
    (web / "index.html").write_text("old")
    _advance(site.repo, "apps/web/src/a.ts")
    assert site.run("--auto", STUB_PLAN="web restart").returncode == 1
    assert "web build failed" in site.state("blocked").read_text()
    assert (web / "index.html").read_text() == "old"
    assert not any(c.startswith("launchctl") for c in site.called())


def test_a_changed_plist_writer_notifies_and_never_blocks(site: Site) -> None:
    site.seed()
    (site.agents / "com.algotrade.api.plist").write_text("installed")  # differs from regenerated
    (site.agents / "com.algotrade.deploy.plist").write_text("plist\n")  # same as regenerated
    _advance(site.repo, "apps/ingestion/algotrade_ingestion/ops/schedule.py")
    out = site.run("--auto", STUB_PLAN="plists")
    assert out.returncode == 0, out.stdout + out.stderr
    (notice,) = site.notices()
    assert "reinstall" in notice and "com.algotrade.api" in notice and "nightly" in notice
    assert "com.algotrade.deploy " not in notice and not site.state("blocked").exists()
    assert not any(c.startswith("launchctl") for c in site.called())  # never installs


def test_clear_prints_the_reason_and_lets_it_run_again(site: Site) -> None:
    site.state("blocked").parent.mkdir(parents=True)
    site.state("blocked").write_text("2026-10-08T00:00:00Z the web build failed\n")
    out = site.run("--clear")
    assert out.returncode == 0 and "the web build failed" in out.stdout and "cleared" in out.stdout
    assert not site.state("blocked").exists()
    assert "not blocked" in site.run("--clear").stdout


def test_an_unknown_flag_is_a_usage_error(site: Site) -> None:
    assert site.run("--nope").returncode == 2
