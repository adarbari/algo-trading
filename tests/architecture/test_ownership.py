"""Fitness tests for the ownership registry (ADR 0019).

- every stored table has exactly one producing owner in ``architecture/tables.toml``;
- every path the registry and its ratchets name exists, and every doc section it cites does;
- every L3 site setting is read by code (ignored settings, like ``cboe.workers`` once was,
  are listed in ``KNOWN_UNREAD``, which may only shrink);
- the ownership and duplicate-code ratchets pass on today's tree;
- the restructure is finished: no known violation and no pending contract may remain, so a
  regression cannot be parked silently (a real exception needs an ADR and an ``allowed``
  entry with its reason).
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

from algotrade.storage.tables import schemas
from tests.conftest import REPO_ROOT

REGISTRY = tomllib.loads((REPO_ROOT / "architecture" / "ownership.toml").read_text())
WEB_REGISTRY = tomllib.loads((REPO_ROOT / "architecture" / "web_ownership.toml").read_text())
TABLES = tomllib.loads((REPO_ROOT / "architecture" / "tables.toml").read_text())["table"]
KNOWN = tomllib.loads((REPO_ROOT / "architecture" / "known_violations.toml").read_text())
CODE_FILES = sorted(
    p
    for top in ("src", "libs", "apps")
    for p in (REPO_ROOT / top).rglob("*.py")
    if not {".venv", "node_modules"} & set(p.parts)
)
SITE_SETTINGS = sorted((REPO_ROOT / "config" / "site").glob("*.toml"))
# Typed views of L3 settings (the one loader): every field must be used by code, not only parsed.
TYPED_SETTINGS_FILES = (
    "src/algotrade/config/site/settings.py",
    "src/algotrade/config/site/holdings.py",
    "src/algotrade/config/site/ibkr.py",
    "src/algotrade/config/site/macro.py",
    "src/algotrade/config/site/nightly.py",
)
TYPED_SETTINGS = (
    "SourcesSettings",
    "VendorSettings",
    "UniverseSettings",
    "NightlySettings",
    "ScreeningSettings",
    "BacktestSettings",
    "CostSettings",
    "LimitSettings",
    "IbkrSettings",
    "EtfHoldingsSettings",
    "VerificationSettings",
    "MacroSettings",
)
# Settings that are parsed but drive nothing today. This list may only shrink: wire the
# setting up (docs/roadmap.md, track R) or delete it from config/site, then remove it here.
KNOWN_UNREAD: set[str] = set()


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
    names = Counter(t["name"] for t in TABLES)
    duplicated = [name for name, n in names.items() if n > 1]
    assert not duplicated, f"tables with more than one producing owner: {duplicated}"
    missing = sorted(set(schemas.KNOWN) - set(names))
    assert not missing, f"add a [[table]] entry with its owner to tables.toml: {missing}"


def test_every_open_table_family_has_a_producing_owner() -> None:
    names = [t["name"] for t in TABLES]
    families = [*schemas.OPEN_PREFIXES, "bars/"]
    orphans = [f for f in families if not any(n.startswith(f) for n in names)]
    assert not orphans, f"no producing owner registered for: {orphans}"
    for table in TABLES:
        assert isinstance(table["owner"], str), f"{table['name']}: owner must be ONE module"
        if "*" not in table["name"]:
            schemas.spec_for(table["name"])  # a registered table must be a valid table


# ----------------------------------------------------------------------------- paths


def test_registry_paths_exist() -> None:
    missing = []
    for resp in REGISTRY["responsibility"]:
        missing += [f"{resp['id']}: {g}" for g in resp["owner"] if not _paths_matching(g)]
    for table in TABLES:
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


def test_restructure_is_complete_no_known_violations_or_pending_contracts() -> None:
    """The ratchet is at zero: any ownership hit fails CI, and every planned import contract
    is enforced. Exceptions go through an ADR into ``allowed``, never back into these lists."""
    assert KNOWN.get("violation", []) == [], "known_violations.toml must stay empty (ADR 0019)"
    assert "pending_contract" not in REGISTRY, "enable the contract in pyproject.toml instead"
    for resp in REGISTRY["responsibility"]:
        assert "target_pr" not in resp, f"{resp['id']}: the restructure track is complete"


# ----------------------------------------------------------------------------- settings


def _keys(doc: Mapping[str, Any], prefix: str = "") -> Iterator[str]:
    for key, value in doc.items():
        if isinstance(value, Mapping):
            yield from _keys(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}"


def _code_names() -> tuple[set[str], Counter[str]]:
    """-> (every literal / identifier in code, attribute reads by name outside the loader).

    Reads inside the settings loader (defaults while parsing) do not count as use; its
    methods reading ``self`` (e.g. ``SourcesSettings.vendor``) do."""
    names: set[str] = set()
    attrs: Counter[str] = Counter()
    for path in CODE_FILES:
        loader = path.relative_to(REPO_ROOT).as_posix() in TYPED_SETTINGS_FILES
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
                if (not loader or owner == "self") and owner not in ("cls", "d"):
                    attrs[node.attr] += 1
    return names, attrs


def _typed_fields() -> list[str]:
    fields = []
    classes = {
        n.name: n
        for name in TYPED_SETTINGS_FILES
        for n in ast.parse((REPO_ROOT / name).read_text()).body
        if isinstance(n, ast.ClassDef)
    }
    for cls in TYPED_SETTINGS:
        node = classes[cls]
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


# ----------------------------------------------------------------------------- web app


def test_web_responsibilities_name_existing_owners_and_sections() -> None:
    """ADR 0025: web owners are enforced by lint, not AST rules; the registry stays honest."""
    entries = WEB_REGISTRY.get("web_responsibility", [])
    assert entries, "the web app's responsibilities are registered ([[web_responsibility]])"
    ids = [e["id"] for e in entries] + [r["id"] for r in REGISTRY["responsibility"]]
    assert len(ids) == len(set(ids)), "duplicate responsibility ids"
    for entry in entries:
        assert entry.get("enforced_by"), f"{entry['id']}: name the rule or check enforcing it"
        for pattern in entry["owner"]:
            base = pattern.split("*")[0].rstrip("/")
            assert (REPO_ROOT / base).exists(), f"{entry['id']}: owner {pattern} does not exist"
        doc, _, anchor = entry["section"].partition("#")
        assert anchor in _slugs((REPO_ROOT / doc).read_text()), f"{entry['id']}: {entry['section']}"
