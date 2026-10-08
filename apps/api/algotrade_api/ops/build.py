"""The build identity (ADR 0044, amendment 2026-10-07): which commit and GraphQL schema the
running API started with, which ones the built web was stamped with, and the mismatches
between them and the checkout.

A process keeps serving the code and schema it started with; the web build is read from disk
on every request. So a ``make web-build`` after the API started can serve a web whose queries
ask for fields the running API lacks (2026-10-07: ``FieldGuide.summary``, every Builder row
empty). ``api_stamp`` is taken once in ``create_app`` (the commit of the checkout the code
runs from and a hash of the live schema), ``write_web_stamp`` writes ``build.json`` next to
the build's ``index.html`` (run by ``make web-build`` through ``algotrade-api stamp-web``;
the hash of the committed ``apps/api/schema.graphql`` the web codegen read), and
``mismatches`` compares the three. ``GET /health`` reports them; ``running_mismatches`` asks a
running API for them (``make status``, ``make doctor``, after ``make web-build``). The fix
is always printed, never run: restart the agent (``restart_command``) or rebuild the web.
"""

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from algotrade_api.ops.schedule import restart_command

STAMP = "build.json"  # in the build directory, next to index.html
SCHEMA = Path("apps") / "api" / "schema.graphql"  # the committed snapshot the codegen reads
REPO = Path(__file__).resolve().parents[4]  # ops -> algotrade_api -> api -> apps -> checkout
UNKNOWN = "unknown"
SHORT = 9  # characters of a commit shown in a message


@dataclass(frozen=True)
class Stamp:
    """A commit and a GraphQL schema hash; ``at``: when the API started or the web was built
    (``None`` for the checkout, which has no moment)."""

    git_sha: str
    schema_hash: str
    at: datetime | None = None


@dataclass(frozen=True)
class BuildReport:
    """What ``GET /health`` says about the builds: the three stamps and what disagrees."""

    api: Stamp
    web: Stamp | None
    checkout: Stamp | None
    mismatches: tuple[str, ...]

    @property
    def stale(self) -> bool:
        return bool(self.mismatches)


def schema_hash(sdl: str) -> str:
    """The short hash of a schema's SDL text (live or committed: the same text, the same hash)."""
    return hashlib.sha256(sdl.encode()).hexdigest()[:12]


def git_sha(repo: Path) -> str:
    """The commit checked out at ``repo``; ``unknown`` outside a git checkout."""
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    sha = done.stdout.strip()
    return sha if done.returncode == 0 and sha else UNKNOWN


def api_stamp(sdl: str, repo: Path = REPO, now: datetime | None = None) -> Stamp:
    """The running API's identity, taken once at startup: its checkout's commit, its schema."""
    return Stamp(git_sha(repo), schema_hash(sdl), now or datetime.now(UTC))


def checkout_stamp(repo: Path = REPO) -> Stamp | None:
    """The checkout as it is now (commit, committed schema); ``None`` without the schema file
    (an installed package, not a checkout)."""
    try:
        text = (repo / SCHEMA).read_text()
    except OSError:
        return None
    return Stamp(git_sha(repo), schema_hash(text))


def write_web_stamp(dist: Path, repo: Path = REPO, now: datetime | None = None) -> Stamp:
    """Stamp the build in ``dist`` with the checkout it was built from; the stamp written."""
    checkout = checkout_stamp(repo)
    if checkout is None:
        raise FileNotFoundError(f"{repo / SCHEMA}: not a checkout, nothing to stamp the web with")
    stamp = Stamp(checkout.git_sha, checkout.schema_hash, now or datetime.now(UTC))
    body = {"git_sha": stamp.git_sha, "schema_hash": stamp.schema_hash, "built_at": _iso(stamp)}
    (dist / STAMP).write_text(json.dumps(body, indent=2) + "\n")
    return stamp


def read_web_stamp(dist: Path) -> Stamp | None:
    """The stamp of the build in ``dist``; ``None`` when it has none or it does not parse."""
    try:
        body = json.loads((dist / STAMP).read_text())
        return Stamp(
            str(body["git_sha"]),
            str(body["schema_hash"]),
            datetime.fromisoformat(str(body["built_at"])),
        )
    except (OSError, ValueError, LookupError, TypeError):
        return None


def mismatches(
    api: Stamp, web: Stamp | None, checkout: Stamp | None, *, serves_web: bool
) -> tuple[str, ...]:
    """Each way the running API disagrees with the web it serves or its checkout, with the fix;
    empty when they agree. ``serves_web``: whether ``ALGOTRADE_WEB_DIST`` is set."""
    restart = f"restart the API: {restart_command()}"
    out: list[str] = []
    if serves_web and web is None:
        out.append(f"the served web has no {STAMP} (built outside make web-build): make web-build")
    elif web is not None and web.schema_hash != api.schema_hash:
        newer = web.at is not None and api.at is not None and web.at > api.at
        out.append(
            f"the web was built against GraphQL schema {web.schema_hash}, the API serves "
            f"{api.schema_hash}: its queries can ask for fields the API lacks; "
            + (restart if newer else "rebuild the web: make web-build")
        )
    if checkout is None:
        return tuple(out)
    if checkout.schema_hash != api.schema_hash:
        out.append(
            f"the checkout's {SCHEMA.as_posix()} is {checkout.schema_hash}, the API serves "
            f"{api.schema_hash}; {restart}"
        )
    elif UNKNOWN not in (api.git_sha, checkout.git_sha) and checkout.git_sha != api.git_sha:
        out.append(
            f"the API runs commit {api.git_sha[:SHORT]}, the checkout is at "
            f"{checkout.git_sha[:SHORT]}; {restart}"
        )
    return tuple(out)


def build_status(api: Stamp, web_dist: Path | None, repo: Path = REPO) -> BuildReport:
    """The report ``GET /health`` serves: the web stamp and the checkout read now (both change
    under a running API), compared with the stamp the API started with."""
    web = read_web_stamp(web_dist) if web_dist is not None else None
    checkout = checkout_stamp(repo)
    return BuildReport(
        api, web, checkout, mismatches(api, web, checkout, serves_web=web_dist is not None)
    )


Fetch = Callable[[str], bytes]


def fetch_http(url: str) -> bytes:
    with urlopen(url, timeout=2) as response:
        return bytes(response.read())


def running_mismatches(base_url: str, fetch: Fetch = fetch_http) -> tuple[str, ...] | None:
    """What the API answering at ``base_url`` reports out of step; ``None`` when none answers.
    An API from before build identity (no ``build`` in its health) is itself out of step."""
    try:
        health = json.loads(fetch(f"{base_url}/health"))
    except (OSError, URLError, ValueError):
        return None
    build = health.get("build") if isinstance(health, dict) else None
    if not isinstance(build, dict):
        return (
            f"the API reports no build identity (it predates it); restart it: {restart_command()}",
        )
    return tuple(str(m) for m in build.get("mismatches") or ())


def _iso(stamp: Stamp) -> str:
    assert stamp.at is not None
    return stamp.at.isoformat()
