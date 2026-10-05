#!/usr/bin/env python3
"""The REST GET allow-list only shrinks (ADR 0037): page reads move to GraphQL.

``architecture/rest_allowlist.toml`` lists every GET route the API may serve and commits
their number as ``max_get_routes``. This script checks the file is well formed and that the
number of entries equals the committed count:

- more entries than the count fails: a new read for a page is a GraphQL field
  (``.claude/skills/add-graphql-field``), not a REST GET;
- fewer entries fails too until the count is lowered (``--update``, ``make
  rest-allowlist-update``), so a retired route can never silently come back.

``--update`` lowers ``max_get_routes`` to the number of entries and refuses to raise it.
That every served GET route is listed (and every entry served) is
``tests/architecture/api/test_rest_allowlist.py::test_rest_get_routes_are_allowlisted``.

Usage: python scripts/check_rest_allowlist.py [--root DIR] [--update]
Stdlib only, so it runs before (and without) the project environment.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ALLOWLIST = Path("architecture/rest_allowlist.toml")
COUNT = re.compile(r"^max_get_routes = \d+$", flags=re.MULTILINE)


def problems(data: dict[str, Any]) -> list[str]:
    """Malformed entries: each is a GET with a path; `keep` routes say why, others when they go."""
    out = []
    paths = [r.get("path") for r in data.get("route", [])]
    out += [f"{p}: listed twice" for p in sorted({p for p in paths if paths.count(p) > 1})]
    for route in data.get("route", []):
        where = route.get("path", "<no path>")
        if route.get("method") != "GET":
            out.append(f"{where}: method must be GET (writes are REST by rule and not listed)")
        if not isinstance(route.get("keep"), bool):
            out.append(f"{where}: keep must be true or false")
        elif route["keep"] and not route.get("reason"):
            out.append(f"{where}: a route that stays REST needs its reason")
        elif not route["keep"] and not route.get("retire_in"):
            out.append(f"{where}: a route that retires names the PR (retire_in)")
    if not isinstance(data.get("max_get_routes"), int):
        out.append("max_get_routes (the committed count) is missing")
    return out


def check(root: Path, update: bool) -> tuple[int, str]:
    path = root / ALLOWLIST
    text = path.read_text()
    data = tomllib.loads(text)
    bad = problems(data)
    if bad:
        return 1, f"{ALLOWLIST} is malformed:\n  " + "\n  ".join(bad)
    listed, committed = len(data.get("route", [])), data["max_get_routes"]
    if listed > committed:
        return 1, (
            f"{ALLOWLIST} lists {listed} GET routes, the committed maximum is {committed}. "
            "The allow-list only shrinks: a read for a page is a GraphQL field "
            "(.claude/skills/add-graphql-field), not a new REST GET (ADR 0037)."
        )
    if listed < committed:
        if not update:
            return 1, (
                f"{ALLOWLIST} lists {listed} GET routes but commits {committed}: good news, "
                "lower the count with `make rest-allowlist-update`."
            )
        path.write_text(COUNT.sub(f"max_get_routes = {listed}", text, count=1))
        return 0, f"{ALLOWLIST}: max_get_routes lowered from {committed} to {listed}."
    return 0, f"rest allow-list: OK ({listed} GET routes, shrink-only)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--update", action="store_true", help="lower the committed count")
    args = parser.parse_args(argv)
    code, message = check(args.root, args.update)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
