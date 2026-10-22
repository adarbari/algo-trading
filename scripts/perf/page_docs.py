"""Keeps the recorded operation documents of `benchmarks/api_latency_pages.json` equal to the web's.

The benchmark replays recorded documents; a hand recording drifts from what the web sends (a
selection dropped, a variable renamed) and the numbers then measure something no page asks. The
web's own documents are the generated `gql.ts`; `check` lists every recorded operation whose
document (whitespace aside) or variable names differ from it, `sync` rewrites the recorded
documents from it (no server, no store; the variable values stay as captured). CLI:
`python scripts/perf/page_docs.py [--write]` (`make api-latency-docs`).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load
import web_page_ops as wpo

REPO = Path(__file__).resolve().parents[2]
WEB_SRC = REPO / "apps/web/src"
PAGES_FILE = REPO / "benchmarks/api_latency_pages.json"
GQL_TS = REPO / "apps/web/src/shared/api/generated/graphql/gql.ts"
_HEAD_VARS = re.compile(r"\b(?:query|mutation)\s+\w+\s*\(([^)]*)\)")


def squash(text: str) -> str:
    """The document with its whitespace collapsed (formatting is not a difference)."""
    return re.sub(r"\s+", " ", text).strip()


def declared_variables(document: str) -> set[str]:
    """The variable names an operation declares in its header (`$limit: Int!` -> `limit`)."""
    head = _HEAD_VARS.search(document)
    return set(re.findall(r"\$(\w+)", head.group(1))) if head else set()


def web_documents() -> dict[str, str]:
    """Operation name -> the web's generated document."""
    return load.parse_documents(GQL_TS.read_text())


def drift(
    pages: dict[str, list[dict]], docs: dict[str, str], hand_written: set[str] = frozenset()
) -> list[str]:
    """One line per recorded graphql call that differs from the web's document of its name.

    A name in ``hand_written`` (a typed document string in the web source, interpolated, so not in
    gql.ts) is the web's own but is not compared: only a name found nowhere is flagged."""
    problems: list[str] = []
    for route, calls in pages.items():
        for call in calls:
            if call["kind"] != "graphql":
                continue
            name, doc = call["op"], docs.get(call["op"])
            if doc is None and name in hand_written:
                continue
            if doc is None:
                problems.append(f"{route} {name}: not a web operation (gql.ts has no such name)")
            elif squash(call["query"]) != squash(doc):
                problems.append(f"{route} {name}: the recorded document differs from gql.ts")
            elif set(call["variables"]) != declared_variables(doc):
                problems.append(
                    f"{route} {name}: recorded variables {sorted(call['variables'])} "
                    f"!= declared {sorted(declared_variables(doc))}"
                )
    return problems


def sync(pages: dict[str, list[dict]], docs: dict[str, str]) -> None:
    """Replace each recorded document with the web's (a name gql.ts lacks is left)."""
    for calls in pages.values():
        for call in calls:
            if call["kind"] == "graphql" and call["op"] in docs:
                call["query"] = docs[call["op"]]


def main(argv: list[str]) -> int:
    """Print the drift (`--write`: sync first); 1 when drift remains."""
    doc = json.loads(PAGES_FILE.read_text())
    if "--write" in argv:
        sync(doc["pages"], web_documents())
        PAGES_FILE.write_text(f"{json.dumps(doc, indent=1)}\n")
    problems = drift(doc["pages"], web_documents(), wpo.all_query_ops(WEB_SRC))
    print("\n".join(problems) or "recorded documents match the web's")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
