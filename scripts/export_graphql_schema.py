#!/usr/bin/env python3
"""Write the GraphQL schema (SDL) to ``apps/api/schema.graphql`` (the web codegen's input).

Run after changing a type, a field or a scalar in ``apps/api/algotrade_api/graphql/``, commit
the result, then regenerate the web client (``npm run api:generate`` in apps/web).
``--check`` exits 1 when the committed file is stale (a test does the same in CI).
Usage: python scripts/export_graphql_schema.py [--check]
"""

import argparse
import sys
from pathlib import Path

from algotrade_api.graphql.schema import sdl

TARGET = Path(__file__).resolve().parents[1] / "apps" / "api" / "schema.graphql"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()
    text = sdl()
    if args.check:
        stale = not TARGET.exists() or TARGET.read_text() != text
        print(
            f"{TARGET}: {'stale; run scripts/export_graphql_schema.py' if stale else 'up to date'}"
        )
        return 1 if stale else 0
    TARGET.write_text(text)
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
