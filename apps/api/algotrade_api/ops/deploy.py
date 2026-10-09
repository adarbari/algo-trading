"""The deploy cycle's decisions (ADR 0057): what a change needs, and whether the running site
matches the commit just deployed.

``scripts/ops/deploy.sh`` orchestrates (git, build, swap, notify, log) and asks this module
what bash should not decide: ``actions`` maps the changed paths to what must run, ``verify``
polls the running API's ``/health`` until it serves the deployed commit with no mismatch
(``ops/build.py``). The locks it runs under are the ingestion app's
(``algotrade-ingest deploy-hold``); ``holds_ingest`` says whether a change needs the ingest
run lock too (only when it touches something a running ingest loads). Nothing here installs
or restarts an agent: the script does, and the launchd plists are written by ``ops/schedule.py``.
"""

import json
import threading
from collections.abc import Callable, Iterable
from enum import StrEnum
from fnmatch import fnmatchcase

from algotrade_api.ops.build import Fetch, running_mismatches

PLIST_WRITERS = (
    "apps/ingestion/algotrade_ingestion/ops/schedule.py",
    "apps/api/algotrade_api/ops/schedule.py",
)


class Action(StrEnum):
    """What a deploy does; the member order is the execution order."""

    SYNC = "sync"  # uv sync: dependencies changed
    WEB = "web"  # rebuild the web and swap it in
    RESTART = "restart"  # restart the API agent
    PLISTS = "plists"  # a launchd plist writer changed: tell the owner to reinstall


# First matching rule wins per path; a path may need several actions, a path that matches
# nothing (apps/ingestion/**, docs, tests, ...) needs none: the merge alone is its deploy.
_RULES: tuple[tuple[tuple[str, ...], frozenset[Action]], ...] = (
    (("uv.lock", "*/pyproject.toml", "pyproject.toml", ".python-version"),
     frozenset({Action.SYNC, Action.RESTART})),
    (("apps/web/*", "Makefile"), frozenset({Action.WEB})),
    (("apps/api/schema.graphql",), frozenset({Action.WEB, Action.RESTART})),
    (("apps/api/*", "src/*", "libs/*", "config/site/*"), frozenset({Action.RESTART})),
)  # fmt: skip


def _needs(path: str) -> set[Action]:
    out: set[Action] = set()
    for patterns, actions in _RULES:
        if any(fnmatchcase(path, p) for p in patterns):
            out |= actions
            break
    if path in PLIST_WRITERS:
        out.add(Action.PLISTS)
    return out


def actions(paths: Iterable[str]) -> list[Action]:
    """The union of what the changed ``paths`` need, in execution order."""
    needed: set[Action] = set()
    for path in paths:
        needed |= _needs(path)
    return [a for a in Action if a in needed]


# Paths a running ingest never loads (it imports src/, libs/, apps/ingestion and reads config/;
# apps never import each other and the API only reads stores). Deny by default: a path matching
# none of these, or a new folder, makes the deploy wait for the ingest (owner decision 2026-10-09).
_INGEST_FREE = (
    "apps/web/*",
    "apps/api/*",
    "docs/*",
    "tests/*",
    ".claude/*",
    ".github/*",
    "architecture/*",
    "datasets/golden/*",
)


def _ingest_free(path: str) -> bool:
    if Action.SYNC in _needs(path):  # uv sync rewrites the venv the ingest runs from
        return False
    if "/" not in path:  # root files: only top-level markdown
        return path.endswith(".md")
    return any(fnmatchcase(path, p) for p in _INGEST_FREE)


def holds_ingest(paths: Iterable[str]) -> bool:
    """Whether a deploy of the changed ``paths`` must also take the ingest run lock: ``True``
    unless every path is one a running ingest never loads (web, API, docs, tests, harness,
    root ``*.md``); a dependency change, an unknown path or a new folder holds it. An empty
    diff holds nothing."""
    return not all(_ingest_free(p) for p in paths)


CHECKS = ("api", "full", "web")
_PAUSE = threading.Event()  # never set: ``wait(s)`` is a plain pause (not a rate limit)


def _problems(url: str, expect_sha: str, fetch: Fetch, check: str) -> list[str] | None:
    """What keeps the site from being the deployed commit; ``None``: nothing answers yet.
    ``api``: only the running API's commit (the web is still the old build); ``full``: also no
    mismatch from ``ops/build.py``; ``web``: only the served web stamped with the commit (a
    web-only deploy leaves the API, and so its mismatches, at the previous commit; after a
    restart the ``api`` / ``full`` check already verified it)."""
    found = running_mismatches(url, fetch)
    if found is None:
        return None
    out = list(found) if check == "full" else []
    try:
        build = json.loads(fetch(f"{url}/health"))["build"]
    except (OSError, ValueError, LookupError, TypeError):
        return None
    for name in ("web",) if check == "web" else ("api",):
        stamp = build.get(name)
        sha = str(stamp.get("git_sha", "")) if isinstance(stamp, dict) else ""
        if not sha or not (sha.startswith(expect_sha) or expect_sha.startswith(sha)):
            out.append(f"the {name} is at commit {sha[:9] or 'unknown'}, expected {expect_sha[:9]}")
    return out


def verify(
    url: str,
    expect_sha: str,
    fetch: Fetch,
    check: str = "full",
    tries: int = 45,
    sleep: Callable[[float], object] = _PAUSE.wait,
    delay_s: float = 2.0,
) -> list[str]:
    """Poll the API at ``url`` until ``check`` (see ``_problems``) finds nothing wrong; ``[]``
    on success, else what was still wrong after ``tries`` attempts (a single line when nothing
    answered). The API needs a few seconds to come back after a restart."""
    if check not in CHECKS:
        raise ValueError(f"check must be one of {CHECKS}, not {check!r}")
    last: list[str] | None = None
    for attempt in range(tries):
        last = _problems(url, expect_sha, fetch, check)
        if last == []:
            return []
        if attempt + 1 < tries:
            sleep(delay_s)
    return last or [f"no API answering at {url}"]
