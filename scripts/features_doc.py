#!/usr/bin/env python3
"""Write the feature catalogue (docs/data/features.md) from the feature registry and the
repository's config/site/features/*.toml, and the field guide (docs/data/field-guide.md) from
config/site/field_guide/*.toml.

Usage: python scripts/features_doc.py [--check]
--check exits 1 when the committed file is out of date (tests/architecture/test_features.py
checks the same in CI).
"""

import argparse
import sys
from pathlib import Path

from algotrade.config.site.settings import load_field_guide
from algotrade.features.catalogue import PATH, render
from algotrade.features.guide import PATH as GUIDE_PATH
from algotrade.features.guide import render as render_guide
from algotrade.features.site import site_features
from algotrade.storage.configs.files import FileConfigStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()
    store = FileConfigStore(ROOT / "config")
    pages = {PATH: render(site_features(store)), GUIDE_PATH: render_guide(load_field_guide(store))}
    stale = []
    for rel, text in pages.items():
        path = ROOT / rel
        current = path.read_text() if path.exists() else ""
        if args.check:
            if current != text:
                stale.append(rel)
            continue
        path.write_text(text)
        print(f"wrote {rel}")
    if stale:
        print(f"{', '.join(stale)} out of date: run `make features-doc`")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
