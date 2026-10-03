#!/usr/bin/env python3
"""Write the feature catalogue (docs/data/features.md) from the feature registry and the
repository's config/site/features/*.toml.

Usage: python scripts/features_doc.py [--check]
--check exits 1 when the committed file is out of date (tests/architecture/test_features.py
checks the same in CI).
"""

import argparse
import sys
from pathlib import Path

from algotrade.features.catalogue import PATH, render
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()
    path = ROOT / PATH
    text = render(site_features(FileConfigStore(ROOT / "config")))
    if args.check:
        current = path.read_text() if path.exists() else ""
        if current != text:
            print(f"{PATH} is out of date: run `make features-doc`")
            return 1
        return 0
    path.write_text(text)
    print(f"wrote {PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
