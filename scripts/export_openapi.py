#!/usr/bin/env python3
"""Write the API's OpenAPI document to ``apps/api/openapi.json`` (the web client's input).

Run after changing a route or a response schema, commit the result, then regenerate the web
client. ``--check`` exits 1 when the committed file is stale (a test does the same in CI).
Usage: python scripts/export_openapi.py [--check]
"""

import argparse
import sys
from pathlib import Path

from algotrade_api.main import openapi_json

TARGET = Path(__file__).resolve().parents[1] / "apps" / "api" / "openapi.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()
    text = openapi_json()
    if args.check:
        stale = not TARGET.exists() or TARGET.read_text() != text
        print(f"{TARGET}: {'stale; run scripts/export_openapi.py' if stale else 'up to date'}")
        return 1 if stale else 0
    TARGET.write_text(text)
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
