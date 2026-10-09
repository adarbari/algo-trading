"""The deploy cycle's decisions (ADR 0057): what a change needs, and whether the running site
matches the commit just deployed.

``scripts/ops/deploy.sh`` orchestrates (git, build, swap, notify, log) and asks this module
what bash should not decide: ``actions`` maps the changed paths to what must run, ``verify``
polls the running API's ``/health`` until it serves the deployed commit with no mismatch
(``ops/build.py``). The locks it runs under are the ingestion app's
(``algotrade-ingest deploy-hold``). Nothing here installs or restarts an agent: the script
does, and the launchd plists are written by ``ops/schedule.py``.
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
