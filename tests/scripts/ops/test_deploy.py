"""`scripts/ops/deploy.sh`: the manual deploy and the launchd cycle (`--auto`, ADR 0057) onto a
release tree (ADR 0079), run against a temp git repo (the main checkout, state root) with a
`var/release/blue` worktree and stub tools on PATH (no network, no launchctl, no real build)."""

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
    n=$(cat "$STUB_LOG.plans" 2>/dev/null || echo 0); echo $((n + 1)) > "$STUB_LOG.plans"
    if [ -n "$STUB_PLAN_FAIL_SECOND" ] && [ "$n" -ge 1 ]; then exit 1; fi
    case " $* " in
      *" --ingest-sync "*) echo "${STUB_HINT-}" ;;
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
shift
case " $* " in
  *" --deploy-only "*) ;;
  *) if [ -n "$STUB_INGEST_HELD" ]; then exit 75; fi ;;  # an ingest run holds its lock
esac
[ "$1" = --deploy-only ] && shift; [ "$1" = -- ] && shift
if [ -n "$STUB_BUSY" ]; then exit 75; fi
exec "$@"
"""
MAKE_STUB = """#!/bin/sh
echo "make $*" >> "$STUB_LOG"
prev=""
for a in "$@"; do
  case "$a" in
    WEB_DIST=*) d="${a#WEB_DIST=}"; mkdir -p "$d/assets"; echo new > "$d/index.html"
                echo new > "$d/assets/new.js" ;;
  esac
  if [ "$prev" = -C ]; then tree="$a"; fi
  prev="$a"
done
# Vite bakes the VITE_* values of the tree's apps/web/.env.local into the bundle
if [ -z "$STUB_MAKE_NO_ENV" ] && [ -n "$d" ] && [ -f "$tree/apps/web/.env.local" ]; then
  cat "$tree/apps/web/.env.local" >> "$d/assets/new.js"
fi
"""
UV_STUB = """#!/bin/sh
echo "uv $* (cwd=$PWD)" >> "$STUB_LOG"
if [ "$PWD" = "$STUB_MAIN" ]; then
  if [ -n "$STUB_UV_MAIN_FAIL" ]; then exit 1; fi
  if [ -n "$STUB_UV_MAIN_FAIL_ONCE" ] && [ ! -f "$STUB_LOG.uvfailed" ]; then
    touch "$STUB_LOG.uvfailed"; exit 1
  fi
fi
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
    (repo / ".gitignore").write_text(
        "*.local.toml\n/var\nvar/\n/config/users\n.env\n.env.local\n.env.*.local\n"
    )
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
        self._stub("uv", UV_STUB)
        for name in ("npm", "node", "curl", "launchctl"):
            self._stub(name, LOGGING_STUB)
        self.agents = tmp_path / "agents"
        self.agents.mkdir()
        self.tree = self.repo / "var" / "release" / "blue"
        self.tree.parent.mkdir(parents=True)
        _git(self.repo, "worktree", "add", "-q", "--detach", str(self.tree))
        (self.tree.parent / "current").symlink_to("blue")
        self.env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "STUB_LOG": str(self.calls),
            "ALGOTRADE_DEPLOY_API": str(self.bin / "algotrade-api"),
            "ALGOTRADE_DEPLOY_INGEST": str(self.bin / "algotrade-ingest"),
            "ALGOTRADE_DEPLOY_NOTIFY": str(self.bin / "notify"),
            "ALGOTRADE_DEPLOY_AGENTS": str(self.agents),
            "STUB_MAIN": str(self.repo.resolve()),
            "ALGOTRADE_DEPLOY_FREE_KB": "100000000",  # 100 GB: the floor test lowers it
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

    def served(self) -> str:
        """The commit the release tree is at."""
        return _git(self.tree, "rev-parse", "HEAD")

    def seed(self) -> str:
        sha = _git(self.repo, "rev-parse", "HEAD")
        self.state("last_sha").parent.mkdir(parents=True, exist_ok=True)
        self.state("last_sha").write_text(sha + "\n")
        return sha

    @property
    def web(self) -> Path:
        return self.repo / "var" / "release" / "blue.web"

    def log(self) -> str:
        path = self.repo / "var" / "logs" / "deploy.log"
        return path.read_text() if path.exists() else ""


@pytest.fixture
def site(tmp_path: Path) -> Site:
    return Site(tmp_path)


# ---- the manual deploy -----------------------------------------------------------------------


def test_the_main_checkout_never_blocks_serving(site: Site) -> None:
    """ADR 0079: off main, dirty or diverged, the main checkout is the ingest's, not serving's."""
    _git(site.repo, "switch", "-qc", "feat/x")
    (site.repo / "a.txt").write_text("changed\n")
    (site.repo / "b.txt").write_text("b\n")
    _git(site.repo, "add", "b.txt")
    _git(site.repo, "commit", "-qm", "local only")
    out = site.run("--dry-run")
    assert out.returncode == 0, out.stderr


def test_a_missing_release_tree_refuses_and_names_init_release(site: Site) -> None:
    _git(site.repo, "worktree", "remove", "--force", str(site.tree))
    out = site.run("--dry-run")
    assert out.returncode == 1 and "--init-release" in out.stderr


def test_dry_run_prints_the_whole_plan_and_runs_nothing(site: Site) -> None:
    out = site.run("--dry-run")
    assert out.returncode == 0, out.stderr
    plan = [x for x in out.stdout.splitlines() if x.startswith("[dry-run]")]
    heads = [x.split()[1] for x in plan]
    assert [Path(h).name for h in heads] == [
        "link", "git", "git", "uv", "make", "launchctl", "algotrade-api", "swap", "algotrade-api",
        "ingest",
    ]  # fmt: skip
    assert "checkout -q --force --detach" in plan[1] and "reset -q --hard" in plan[2]
    assert "sync --all-packages --locked" in plan[3]
    assert "web-build" in plan[4] and "kickstart -k" in plan[5]
    assert "--check api" in plan[6] and "--check web" in plan[8]
    assert "locks (dry-run): deploy\n" in out.stdout
    assert site.called() == [] and not site.state("last_sha").exists()


def test_a_manual_deploy_does_everything_and_records_the_commit(site: Site) -> None:
    sha = _advance(site.repo, "src/algotrade/x.py")
    out = site.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert site.called()[0].startswith("ingest deploy-hold --deploy-only -- bash ")
    assert any(c.startswith("uv sync --all-packages --locked") for c in site.called())
    assert site.state("last_sha").read_text().strip() == sha
    assert site.served() == sha  # the release tree moved
    assert _git(site.repo, "rev-parse", "HEAD") == sha  # and so did the ingest checkout (R2)
    assert (site.web / "index.html").read_text().strip() == "new"


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


def test_the_first_run_seeds_last_sha_from_the_release_tree(site: Site) -> None:
    head = site.served()
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


def test_a_missing_release_tree_blocks_and_notifies_once(site: Site) -> None:
    _git(site.repo, "worktree", "remove", "--force", str(site.tree))
    out = site.run("--auto")
    assert out.returncode == 1 and "--init-release" in site.state("blocked").read_text()
    assert len(site.notices()) == 1 and "--clear" in site.notices()[0]
    again = site.run("--auto")
    assert again.returncode == 0 and len(site.notices()) == 1  # stopped until cleared


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
    assert site.served() == sha
    assert f"deployed {sha[:9]} (restart)" in site.log()


def test_a_web_change_is_built_aside_and_swapped_in_keeping_old_assets(site: Site) -> None:
    site.seed()
    web = site.web
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
    assert "old.js" in (site.repo / "var" / "release" / "blue.web.prev" / "index.html").read_text()
    calls = site.called()
    assert any(f"make -C {site.tree} web-build WEB_DIST={web}.next" in c for c in calls)
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
    assert "skipped: deploy running" in site.log()
    assert site.state("last_sha").read_text().strip() == before
    assert not site.state("blocked").exists() and site.notices() == []
    assert site.served() == before


def test_a_deploy_during_a_held_ingest_lock_deploys(site: Site) -> None:
    """The regression (2026-10-20): back-to-back backfills held the ingest lock and a diff
    touching apps/ingestion and config/site made every cycle skip for hours. A serving deploy
    takes the deploy lock alone, so it goes ahead whatever the ingest is doing."""
    site.seed()
    _advance(site.repo, "apps/ingestion/algotrade_ingestion/a.py")
    sha = _advance(site.repo, "config/site/sources.toml")
    out = site.run("--auto", STUB_PLAN="restart", STUB_INGEST_HELD="1")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "skipped" not in site.log() and f"deployed {sha[:9]}" in site.log()
    assert site.served() == sha and site.state("last_sha").read_text().strip() == sha
    holds = [c for c in site.called() if c.startswith("ingest deploy-hold --deploy-only")]
    assert holds and "--ingest-apply" not in holds[0]  # serving: the deploy lock alone
    assert _git(site.repo, "rev-parse", "HEAD") != sha  # the busy ingest lock kept main back
    assert not any("--locks" in c for c in site.called())  # the plan no longer decides locks


def test_a_busy_deploy_lock_skips_and_names_the_deploy(site: Site) -> None:
    site.seed()
    _advance(site.repo, "apps/web/src/a.ts")
    assert site.run("--auto", STUB_PLAN="web", STUB_BUSY="1").returncode == 0
    assert "skipped: deploy running" in site.log()
    assert "ingest/deploy" not in site.log()


def test_the_private_ref_is_fetched_and_origin_main_is_left_alone(site: Site) -> None:
    """ADR 0079 step 4: `--refmap=` keeps the deployer from writing refs/remotes/origin/main,
    which sessions sharing the object store fetch too (`cannot lock ref`)."""
    site.seed()
    before = _git(site.repo, "rev-parse", "refs/remotes/origin/main")
    sha = _advance(site.repo, "src/algotrade/x.py")
    assert site.run("--auto").returncode == 0
    assert _git(site.repo, "rev-parse", "refs/remotes/origin/main") == before
    assert _git(site.repo, "rev-parse", "refs/deploy/main") == sha


def test_the_release_tree_is_clean_and_the_overlay_links_stay_out_of_git_status(
    site: Site,
) -> None:
    (site.repo / "llm.local.toml").write_text("enabled = true\n")
    (site.repo / "config" / "site").mkdir(parents=True)
    (site.repo / "config" / "site" / "llm.local.toml").write_text("enabled = true\n")
    (site.repo / "config" / "users").mkdir()
    (site.repo / ".env").write_text("X=1\n")
    site.seed()
    _advance(site.repo, "src/algotrade/x.py")
    assert site.run("--auto").returncode == 0
    assert _git(site.tree, "status", "--porcelain") == ""  # untracked and ignored: nothing at all
    assert _git(site.tree, "status", "--porcelain", "-uno") == ""
    for name in ("var", ".env", "config/users", "config/site/llm.local.toml"):
        assert (site.tree / name).is_symlink(), name
    assert (site.tree / "var").resolve() == (site.repo / "var").resolve()
    assert site.run("--auto").returncode == 0  # the links are checked each cycle, not recreated


def test_a_deploy_builds_the_web_with_the_apps_web_env_files_visible(site: Site) -> None:
    """Regression (2026-10-20): the web built in the release tree had no VITE_SUPABASE_*, because
    the git-ignored apps/web/.env.local was not linked in: sign-in said "not set up"."""
    web_dir = site.repo / "apps" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / ".env.local").write_text("VITE_SUPABASE_URL=https://x.supabase.co\n")
    (web_dir / ".env.production.local").write_text("VITE_SUPABASE_ANON_KEY=key\n")
    site.seed()
    _advance(site.repo, "apps/web/src/a.ts")
    out = site.run("--auto", STUB_PLAN="web")
    assert out.returncode == 0, out.stdout + out.stderr
    bundle = (site.web / "assets" / "new.js").read_text()
    assert "VITE_SUPABASE_URL=https://x.supabase.co" in bundle
    for name in (".env.local", ".env.production.local"):
        assert (site.tree / "apps" / "web" / name).is_symlink(), name
    assert _git(site.tree, "status", "--porcelain") == ""  # the links stay out of git status


def test_a_web_build_without_the_supabase_url_is_never_swapped_in(site: Site) -> None:
    web_dir = site.repo / "apps" / "web"
    web_dir.mkdir(parents=True)
    (web_dir / ".env.local").write_text("VITE_SUPABASE_URL=https://x.supabase.co\n")
    live = site.web
    live.mkdir(parents=True)
    (live / "index.html").write_text("old")
    site.seed()
    _advance(site.repo, "apps/web/src/a.ts")
    out = site.run("--auto", STUB_PLAN="web", STUB_MAKE_NO_ENV="1")
    assert out.returncode == 1 and "lacks VITE_SUPABASE_URL" in site.state("blocked").read_text()
    assert (live / "index.html").read_text() == "old"


def test_every_ignored_apps_web_env_file_is_in_the_overlay_list() -> None:
    """Whatever apps/web/.gitignore (and the root .gitignore) ignores that Vite reads is linked."""
    root = SCRIPT.parents[2]
    ignored = {
        line.strip()
        for line in [
            *(root / "apps" / "web" / ".gitignore").read_text().splitlines(),
            *(root / ".gitignore").read_text().splitlines(),
        ]
        if line.strip().startswith(".env") and line.strip() != ".envrc"
    }
    line = next(x for x in SCRIPT.read_text().splitlines() if x.startswith("WEB_ENV_OVERLAY="))
    overlay = set(line.split("=", 1)[1].strip('"').split())
    assert ignored and ignored <= overlay, ignored - overlay


def test_a_release_tree_with_its_own_var_blocks(site: Site) -> None:
    site.seed()
    (site.tree / "var").mkdir()
    _advance(site.repo, "src/algotrade/x.py")
    assert site.run("--auto").returncode == 1
    assert "its own" in site.state("blocked").read_text()


def test_too_little_free_disk_blocks_before_anything_moves(site: Site) -> None:
    before = site.seed()
    _advance(site.repo, "src/algotrade/x.py")
    out = site.run("--auto", ALGOTRADE_DEPLOY_FREE_KB="1000000")  # 1 GB < the 5 GB floor
    assert out.returncode == 1 and "MB free" in site.state("blocked").read_text()
    assert site.served() == before and not any(c.startswith("launchctl") for c in site.called())


def test_a_dirty_release_tree_is_reset_to_the_target(site: Site) -> None:
    site.seed()
    (site.tree / "a.txt").write_text("edited in the deployer's tree\n")
    sha = _advance(site.repo, "a.txt")  # the target changes the very file that is dirty
    assert site.run("--auto").returncode == 0
    assert _git(site.tree, "status", "--porcelain", "-uno") == "" and site.served() == sha
    assert (site.tree / "a.txt").read_text() == "a.txt"


def test_an_earlier_planned_cycle_does_not_rewind_a_later_deploy(site: Site) -> None:
    site.seed()
    old = _advance(site.repo, "src/a.py")
    new = _advance(site.repo, "src/b.py")
    assert site.run("--auto").returncode == 0 and site.served() == new
    out = site.run("--slot", "blue", "--apply", "auto", old, "restart")
    assert out.returncode == 0 and site.served() == new
    assert site.state("last_sha").read_text().strip() == new
    assert f"skipped: tree already past {old[:9]}" in site.log()


def test_a_release_tree_that_diverged_from_the_target_blocks(site: Site) -> None:
    site.seed()
    (site.tree / "z.txt").write_text("z\n")
    _git(site.tree, "add", "z.txt")
    _git(site.tree, "commit", "-qm", "stray commit in the deployer's tree")
    sha = _advance(site.repo, "src/a.py")
    out = site.run("--auto")
    assert out.returncode == 1 and "has diverged from" in site.state("blocked").read_text()
    assert site.state("last_sha").read_text().strip() != sha


def test_config_users_is_always_linked(site: Site) -> None:
    site.seed()
    _advance(site.repo, "src/a.py")
    assert site.run("--auto").returncode == 0
    assert (site.tree / "config" / "users").is_symlink()
    assert (site.repo / "config" / "users").is_dir()


def test_the_default_slot_follows_current(site: Site) -> None:
    green = site.repo / "var" / "release" / "green"
    _git(site.repo, "worktree", "add", "-q", "--detach", str(green))
    (site.tree.parent / "current").unlink()
    (site.tree.parent / "current").symlink_to("green")
    site.seed()
    sha = _advance(site.repo, "src/a.py")
    assert site.run("--auto").returncode == 0
    assert _git(green, "rev-parse", "HEAD") == sha and site.served() != sha


def test_init_release_never_repoints_current(site: Site) -> None:
    _git(site.repo, "worktree", "remove", "--force", str(site.tree))
    (site.tree.parent / "current").unlink()
    (site.tree.parent / "current").symlink_to("green")
    out = site.run("--init-release", "--slot", "blue")
    assert out.returncode == 1 and "only the blue/green flip" in out.stderr
    assert not site.tree.exists()
    assert (site.tree.parent / "current").readlink() == Path("green")


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
    web = site.web
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
    schedules = [c for c in site.called() if c.startswith("api schedule")]
    assert schedules and all(f"--tree {site.tree}" in c for c in schedules)  # compared as installed
    assert "com.algotrade.deploy " not in notice and not site.state("blocked").exists()
    assert not any(c.startswith("launchctl") for c in site.called())  # never installs


# ---- --init-release ---------------------------------------------------------------------------


def _uninitialised(site: Site) -> None:
    _git(site.repo, "worktree", "remove", "--force", str(site.tree))
    (site.tree.parent / "current").unlink()


def test_init_release_builds_the_tree_carries_assets_and_installs_nothing(site: Site) -> None:
    _uninitialised(site)
    old = site.repo / "var" / "web"
    (old / "assets").mkdir(parents=True)
    (old / "index.html").write_text('<script src="/assets/old.js"></script>')
    (old / "assets" / "old.js").write_text("old")
    sha = _advance(site.repo, "src/algotrade/x.py")
    out = site.run("--init-release")
    assert out.returncode == 0, out.stdout + out.stderr
    assert site.served() == sha and (site.tree.parent / "current").resolve() == site.tree.resolve()
    assert (site.tree / "var").is_symlink() and (site.web / "assets" / "old.js").exists()
    assert (site.web / "assets" / "new.js").exists() and not site.state("last_sha").exists()
    calls = site.called()
    assert any(c.startswith("uv sync --all-packages --locked") for c in calls)
    assert not any(c.startswith(("launchctl", "ingest")) for c in calls)  # installs nothing
    assert "launchctl bootout" in out.stdout and "schedule --agent deploy --tree" in out.stdout
    assert "already exists" in site.run("--init-release").stdout  # once only


def test_init_release_runs_from_the_targets_own_script_when_it_differs(site: Site) -> None:
    _uninitialised(site)
    clone = site.repo.parent / "other"
    _advance(site.repo, "x.txt")
    (clone / "scripts" / "ops").mkdir(parents=True)
    (clone / "scripts" / "ops" / "deploy.sh").write_text(SCRIPT.read_text() + "\n# newer\n")
    _git(clone, "add", ".")
    _git(clone, "commit", "-qm", "R1 lands")
    _git(clone, "push", "-q", "origin", "main")
    out = site.run("--init-release")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "from a temporary worktree" in site.log() and site.tree.exists()
    assert _git(site.repo, "worktree", "list").count("\n") == 1  # the temporary one is gone


def test_init_release_removes_a_half_made_tree_when_the_build_fails(site: Site) -> None:
    _uninitialised(site)
    site._stub("make", "#!/bin/sh\nexit 2\n")
    out = site.run("--init-release")
    assert out.returncode != 0 and "removing the half-made tree" in out.stderr
    assert not site.tree.exists()


# ---- the ingest checkout's own sync (ADR 0079 step 5) -----------------------------------------


def _main_head(site: Site) -> str:
    return _git(site.repo, "rev-parse", "HEAD")


def test_the_ingest_checkout_is_fast_forwarded_under_both_locks_after_a_deploy(site: Site) -> None:
    site.seed()
    sha = _advance(site.repo, "apps/ingestion/algotrade_ingestion/a.py")
    out = site.run("--auto", STUB_HINT="ingest")
    assert out.returncode == 0, out.stdout + out.stderr
    assert _main_head(site) == sha and site.served() == sha
    both = [c for c in site.called() if "--ingest-apply" in c]
    assert both and "--deploy-only" not in both[0] and both[0].startswith("ingest deploy-hold -- ")
    assert "ingest checkout moved" in site.log() and "ingest code changed" in site.log()
    assert not any("(cwd=" + str(site.repo.resolve()) + ")" in c for c in site.called())  # no sync


def test_a_busy_lock_skips_the_ingest_sync_silently_and_an_idle_cycle_applies_it(
    site: Site,
) -> None:
    before = site.seed()
    _advance(site.repo, "src/a.py")
    sha = _advance(site.repo, "src/b.py")
    out = site.run("--auto", STUB_INGEST_HELD="1")  # a run holds the ingest lock
    assert out.returncode == 0 and site.served() == sha
    assert _main_head(site) == before and site.notices() == []
    assert "ingest" not in site.log().replace("deployed", "")  # nothing logged for the skip
    sha2 = _advance(site.repo, "docs/x.md")  # a later cycle with its own, smaller range
    assert site.run("--auto", STUB_INGEST_HELD="1").returncode == 0 and _main_head(site) == before
    assert site.run("--auto").returncode == 0  # the lock is free: HEAD..target spans all three
    assert _main_head(site) == sha2 and site.notices() == []
    idle = site.run("--auto")  # nothing left: no lock is even tried
    assert idle.returncode == 0
    assert sum("--ingest-apply" in c for c in site.called()) == 3


def test_a_change_made_while_busy_is_applied_by_a_cycle_with_nothing_to_serve(site: Site) -> None:
    site.seed()
    sha = _advance(site.repo, "src/a.py")
    assert site.run("--auto", STUB_INGEST_HELD="1").returncode == 0
    assert site.state("last_sha").read_text().strip() == sha
    assert _main_head(site) != sha
    assert site.run("--auto").returncode == 0 and _main_head(site) == sha  # idle cycle


def test_a_dependency_change_syncs_the_ingest_venv_only_then(site: Site) -> None:
    site.seed()
    _advance(site.repo, "src/a.py")
    assert site.run("--auto", STUB_PLAN="restart").returncode == 0
    main_cwd = f"(cwd={site.repo.resolve()})"
    assert not any(c.startswith("uv sync") and c.endswith(main_cwd) for c in site.called())
    _advance(site.repo, "uv.lock")
    assert site.run("--auto", STUB_PLAN="sync restart").returncode == 0
    assert any(c.startswith("uv sync --all-packages --locked") and c.endswith(main_cwd)
               for c in site.called())  # fmt: skip


def test_a_failed_ingest_sync_is_rolled_back_and_never_blocks_serving(site: Site) -> None:
    before = site.seed()
    sha = _advance(site.repo, "uv.lock")
    out = site.run("--auto", STUB_PLAN="sync restart", STUB_UV_MAIN_FAIL="1")
    assert out.returncode == 0 and site.served() == sha and not site.state("blocked").exists()
    assert _main_head(site) == before  # not left half-synced: retried next cycle
    reason = site.state("ingest_sync_blocked").read_text()
    assert "uv sync failed in the ingest checkout" in reason and "venv left inconsistent" in reason
    main_syncs = [
        c
        for c in site.called()
        if c.startswith("uv sync") and c.endswith("(cwd=" + str(site.repo.resolve()) + ")")
    ]
    assert len(main_syncs) == 2  # the failed one, then the old lock put back
    assert len(site.notices()) == 1


def test_a_rolled_back_sync_that_restores_the_old_venv_says_so_plainly(site: Site) -> None:
    before = site.seed()
    _advance(site.repo, "uv.lock")
    assert site.run("--auto", STUB_PLAN="sync restart", STUB_UV_MAIN_FAIL_ONCE="1").returncode == 0
    assert _main_head(site) == before
    reason = site.state("ingest_sync_blocked").read_text()
    assert "uv sync failed" in reason and "inconsistent" not in reason


def test_a_failed_plan_blocks_the_ingest_sync_before_any_merge(site: Site) -> None:
    before = site.seed()
    sha = _advance(site.repo, "uv.lock")
    out = site.run("--auto", STUB_PLAN="sync restart", STUB_PLAN_FAIL_SECOND="1")
    assert out.returncode == 0 and site.served() == sha  # serving unaffected
    assert _main_head(site) == before
    assert not any(
        c.startswith("uv sync") and c.endswith("(cwd=" + str(site.repo.resolve()) + ")")
        for c in site.called()
    )
    assert "deploy-plan failed" in site.state("ingest_sync_blocked").read_text()


def test_a_reason_without_a_sha_notifies_once_across_new_targets(site: Site) -> None:
    site.seed()
    _advance(site.repo, "src/a.py")
    (site.repo / "a.txt").write_text("edited\n")
    site.run("--auto")
    _advance(site.repo, "src/b.py")
    site.run("--auto")
    assert len(site.notices()) == 1


def test_an_index_lock_on_the_ingest_checkout_is_busy_not_a_block(site: Site) -> None:
    before = site.seed()
    sha = _advance(site.repo, "src/a.py")
    (site.repo / ".git" / "index.lock").write_text("")
    out = site.run("--auto")
    (site.repo / ".git" / "index.lock").unlink()
    assert out.returncode == 0 and site.served() == sha
    assert not site.state("ingest_sync_blocked").exists() and site.notices() == []
    assert _main_head(site) == before
    assert site.run("--auto").returncode == 0 and _main_head(site) == sha  # retried


def test_a_serving_block_syncs_the_ingest_checkout_only_to_the_last_served_commit(
    site: Site,
) -> None:
    served = _advance(site.repo, "src/a.py")
    site.state("last_sha").parent.mkdir(parents=True, exist_ok=True)
    assert site.run("--auto").returncode == 0  # seeds last_sha at the tree's HEAD
    site.state("last_sha").write_text(served + "\n")  # the last commit served successfully
    failed = _advance(site.repo, "src/b.py")
    assert site.run("--auto", STUB_VERIFY_RC="1").returncode == 1  # serving blocks at `failed`
    assert site.state("blocked").exists()
    assert site.run("--auto").returncode == 0  # blocked cycle: the ingest sync still runs
    assert _main_head(site) == served != failed  # never the commit serving rejected
    assert site.state("blocked").exists()


def test_a_serving_block_with_no_last_sha_skips_the_ingest_sync(site: Site) -> None:
    before = _main_head(site)
    _advance(site.repo, "src/a.py")
    site.state("blocked").parent.mkdir(parents=True, exist_ok=True)
    site.state("blocked").write_text("x\n")
    assert site.run("--auto").returncode == 0
    assert _main_head(site) == before and site.called() == []


def test_the_default_ingest_program_is_the_release_trees_own(site: Site) -> None:
    site.seed()
    tree_ingest = site.tree / ".venv" / "bin" / "algotrade-ingest"
    tree_ingest.parent.mkdir(parents=True)
    tree_ingest.write_text(
        INGEST_STUB.replace(
            '>> "$STUB_LOG"\n', '>> "$STUB_LOG"\necho from-tree-venv >> "$STUB_LOG"\n', 1
        )
    )
    tree_ingest.chmod(0o755)
    sha = _advance(site.repo, "src/a.py")
    out = site.run("--auto", ALGOTRADE_DEPLOY_INGEST="")
    assert out.returncode == 0, out.stdout + out.stderr
    assert site.served() == sha and "from-tree-venv" in site.called()
    assert _main_head(site) == sha  # the sync's hold came from the same program


@pytest.mark.parametrize("fault", ["dirty", "off-main", "diverged"])
def test_a_main_checkout_that_cannot_sync_notifies_once_per_reason_and_serving_goes_on(
    site: Site, fault: str
) -> None:
    site.seed()
    if fault == "dirty":
        (site.repo / "a.txt").write_text("edited\n")
    elif fault == "off-main":
        _git(site.repo, "switch", "-qc", "feat/x")
    else:
        (site.repo / "b.txt").write_text("b\n")
        _git(site.repo, "add", "b.txt")
        _git(site.repo, "commit", "-qm", "local only")
    first = _advance(site.repo, "src/a.py")
    assert site.run("--auto").returncode == 0 and site.served() == first
    assert not site.state("blocked").exists()  # serving is untouched
    (notice,) = site.notices()
    assert "the ingest checkout cannot sync" in notice
    assert site.state("ingest_sync_blocked").exists()
    second = _advance(site.repo, "src/b.py")
    assert site.run("--auto").returncode == 0 and site.served() == second
    assert len(site.notices()) == 1  # the same reason: no second notification


def test_the_ingest_block_is_cleared_by_the_next_successful_sync(site: Site) -> None:
    site.seed()
    (site.repo / "a.txt").write_text("edited\n")
    _advance(site.repo, "src/a.py")
    assert site.run("--auto").returncode == 0 and site.state("ingest_sync_blocked").exists()
    _git(site.repo, "checkout", "--", "a.txt")
    sha = _advance(site.repo, "src/b.py")
    assert site.run("--auto").returncode == 0
    assert _main_head(site) == sha and not site.state("ingest_sync_blocked").exists()


def test_the_dry_run_names_the_ingest_sync_and_moves_nothing(site: Site) -> None:
    before = _main_head(site)
    _advance(site.repo, "src/a.py")
    out = site.run("--dry-run")
    assert "[dry-run] ingest checkout: fast-forward" in out.stdout
    assert _main_head(site) == before and site.called() == []


def test_clear_prints_the_reason_and_lets_it_run_again(site: Site) -> None:
    site.state("blocked").parent.mkdir(parents=True)
    site.state("blocked").write_text("2026-10-08T00:00:00Z the web build failed\n")
    out = site.run("--clear")
    assert out.returncode == 0 and "the web build failed" in out.stdout and "cleared" in out.stdout
    assert not site.state("blocked").exists()
    assert "not blocked" in site.run("--clear").stdout


def test_an_unknown_flag_is_a_usage_error(site: Site) -> None:
    assert site.run("--nope").returncode == 2
