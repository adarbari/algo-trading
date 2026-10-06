#!/usr/bin/env python3
"""Write the feature catalogue (docs/data/features.md) from the feature registry and the
repository's config/site/features/*.toml, and the field guide (docs/data/field-guide.md) from
config/site/field_guide/*.toml (the index docs/data/field-guide.md and one page per theme under
docs/data/field-guide/; a theme page no longer rendered is removed).

Usage: python scripts/features_doc.py [--check]
Without --check it also lists the catalogue fields that have no field guide entry.
--check exits 1 when the committed file is out of date (tests/architecture/test_features.py
checks the same in CI).
"""

import argparse
import sys
from pathlib import Path

from algotrade.config.site.settings import load_field_guide
from algotrade.features.catalogue import PATH, render
from algotrade.features.guide import DIR as GUIDE_DIR
from algotrade.features.guide import pages as guide_pages
from algotrade.features.site import site_features
from algotrade.services.read.instruments.catalogue import feature_infos
from algotrade.storage.configs.files import FileConfigStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()
    store = FileConfigStore(ROOT / "config")
    pages = {PATH: render(site_features(store)), **guide_pages(load_field_guide(store))}
    stale = []
    for rel, text in pages.items():
        path = ROOT / rel
        current = path.read_text() if path.exists() else ""
        if args.check:
            if current != text:
                stale.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {rel}")
    for extra in sorted((ROOT / GUIDE_DIR).glob("*.md")):  # a theme that was renamed or removed
        rel = str(extra.relative_to(ROOT))
        if rel in pages:
            continue
        if args.check:
            stale.append(rel)
        else:
            extra.unlink()
            print(f"removed {rel}")
    if stale:
        print(f"{', '.join(stale)} out of date: run `make features-doc`")
        return 1
    if not args.check:
        print(unguided_report(store))
    return 0


def unguided_report(store: FileConfigStore) -> str:
    """The catalogue fields with no field guide entry, by source, so coverage is visible
    (`tests/architecture/test_features.py` requires one for every screened or phrased field)."""
    guided = {e.name for e in load_field_guide(store).fields}
    names = [n for n in feature_infos(site_features(store)) if n not in guided]
    by_source: dict[str, list[str]] = {}
    for name in names:
        prefix, _, column = name.rpartition(".")
        by_source.setdefault(prefix, []).append(column)
    lines = [f"{len(names)} catalogue fields have no field guide entry (config/site/field_guide/):"]
    lines += [f"  {prefix}: {', '.join(columns)}" for prefix, columns in by_source.items()]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
