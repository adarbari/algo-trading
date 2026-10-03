"""Fitness tests for the ownership registry (ADR 0019).

- every stored table has exactly one producing owner in ``architecture/ownership.toml``;
- every path the registry and its ratchets name exists, and every doc section it cites does;
- every L3 site setting is read by code (ignored settings, like ``cboe.workers`` once was,
  are listed in ``KNOWN_UNREAD``, which may only shrink);
- the ownership and duplicate-code ratchets pass on today's tree.
"""

import ast
import fnmatch
import re
import subprocess
import sys
import tomllib
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from algotrade.storage import schemas
from tests.conftest import REPO_ROOT

REGISTRY = tomllib.loads((REPO_ROOT / "architecture" / "ownership.toml").read_text())
KNOWN = tomllib.loads((REPO_ROOT / "architecture" / "known_violations.toml").read_text())
CODE_FILES = sorted(
    p for top in ("src", "apps") for p in (REPO_ROOT / top).rglob("*.py") if ".venv" not in p.parts
)
SITE_SETTINGS = sorted((REPO_ROOT / "config" / "site").glob("*.toml"))
# Typed views of L3 settings: every field must be used by code, not only parsed.
TYPED_SETTINGS = {
    "apps/ingestion/algotrade_ingestion/settings.py": "SourcesSettings",
    "apps/ingestion/algotrade_ingestion/settings.py#universe": "UniverseSettings",
}
# Settings that are parsed but drive nothing today. This list may only shrink: wire the
# setting up (docs/roadmap.md, track R) or delete it from config/site, then remove it here.
KNOWN_UNREAD = {
    "SourcesSettings.cboe_enabled",  # chains always run; PR 5 makes nightly honour it
}


def _paths_matching(pattern: str) -> list[Path]:
    return [
        p
        for p in REPO_ROOT.joinpath(*Path(pattern).parts[:1]).rglob("*")
        if p.is_file() and fnmatch.fnmatch(p.relative_to(REPO_ROOT).as_posix(), pattern)
    ]


def _slugs(markdown: str) -> set[str]:
    heads = re.findall(r"^#+\s+(.+)$", markdown, flags=re.MULTILINE)
    return {re.sub(r"[^a-z0-9 -]", "", h.lower()).strip().replace(" ", "-") for h in heads}


# ----------------------------------------------------------------------------- tables


def test_every_known_table_has_exactly_one_producing_owner() -> None:
    names = Counter(t["name"] for t in REGISTRY["table"])
    duplicated = [name for name, n in names.items() if n > 1]
    assert not duplicated, f"tables with more than one producing owner: {duplicated}"
    missing = sorted(set(schemas.KNOWN) - set(names))
    assert not missing, f"add a [[table]] entry with its owner to ownership.toml: {missing}"


def test_every_open_table_family_has_a_producing_owner() -> None:
    names = [t["name"] for t in REGISTRY["table"]]
    families = [*schemas.OPEN_PREFIXES, "bars/"]
    orphans = [f for f in families if not any(n.startswith(f) for n in names)]
    assert not orphans, f"no producing owner registered for: {orphans}"
    for table in REGISTRY["table"]:
        assert isinstance(table["owner"], str), f"{table['name']}: owner must be ONE module"
        if "*" not in table["name"]:
            schemas.spec_for(table["name"])  # a registered table must be a valid table


# ----------------------------------------------------------------------------- paths


def test_registry_paths_exist() -> None:
    missing = []
    for resp in REGISTRY["responsibility"]:
        missing += [f"{resp['id']}: {g}" for g in resp["owner"] if not _paths_matching(g)]
    for table in REGISTRY["table"]:
        for path in [table["owner"], *table.get("also_written_by", [])]:
            if not (REPO_ROOT / path).is_file():
                missing.append(f"table {table['name']}: {path}")
    assert not missing, f"ownership.toml names paths that do not exist: {missing}"


def test_responsibilities_are_unique_and_cite_real_doc_sections() -> None:
    ids = [r["id"] for r in REGISTRY["responsibility"]]
    assert len(ids) == len(set(ids)), "duplicate responsibility ids"
    for resp in REGISTRY["responsibility"]:
        assert resp["detect"], f"{resp['id']}: needs at least one detect rule"
        doc, _, anchor = resp["section"].partition("#")
        assert anchor in _slugs((REPO_ROOT / doc).read_text()), f"{resp['id']}: {resp['section']}"


def test_known_violations_name_existing_files_and_responsibilities() -> None:
    ids = {r["id"] for r in REGISTRY["responsibility"]}
    for entry in KNOWN.get("violation", []):
        assert (REPO_ROOT / entry["file"]).is_file(), entry
        assert entry["responsibility"] in ids, entry
        assert entry["count"] > 0, entry


def test_pending_contracts_name_the_pr_that_enables_them() -> None:
    for contract in REGISTRY["pending_contract"]:
        assert 2 <= contract["enabled_by_pr"] <= 6, contract["name"]
        assert contract["source_modules"] and contract["forbidden_modules"], contract["name"]


# ----------------------------------------------------------------------------- settings


def _keys(doc: Mapping[str, Any], prefix: str = "") -> Iterator[str]:
    for key, value in doc.items():
        if isinstance(value, Mapping):
            yield from _keys(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}"


def _code_names() -> tuple[set[str], Counter[str]]:
    """-> (every literal / identifier in code, attribute reads by name off non-``cls``/``d``)."""
    names: set[str] = set()
    attrs: Counter[str] = Counter()
    for path in CODE_FILES:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.keyword) and node.arg:
                names.add(node.arg)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
                owner = node.value.id if isinstance(node.value, ast.Name) else ""
                if owner not in ("cls", "d"):
                    attrs[node.attr] += 1
    return names, attrs


def _typed_fields() -> list[str]:
    fields = []
    for rel, cls in TYPED_SETTINGS.items():
        tree = ast.parse((REPO_ROOT / rel.partition("#")[0]).read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
        fields += [
            f"{cls}.{s.target.id}"
            for s in node.body
            if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
        ]
    return fields


def test_every_site_setting_key_is_read_by_code() -> None:
    names, _ = _code_names()
    unread = [
        f"{path.name}: {key}"
        for path in SITE_SETTINGS
        for key in _keys(tomllib.loads(path.read_text()))
        if key.rsplit(".", 1)[-1] not in names
    ]
    assert not unread, f"site settings no code reads (wire them up or delete them): {unread}"


def test_every_typed_setting_drives_code() -> None:
    _, attrs = _code_names()
    unused = {f for f in _typed_fields() if attrs[f.split(".", 1)[1]] == 0}
    new = sorted(unused - KNOWN_UNREAD)
    assert not new, f"settings parsed but never used (wire them up or delete them): {new}"
    fixed = sorted(KNOWN_UNREAD - unused)
    assert not fixed, f"now used, remove from KNOWN_UNREAD in this test: {fixed}"


# ----------------------------------------------------------------------------- ratchets


def test_ownership_ratchet_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/check_ownership.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
