"""Only ``storage/configs/generation.py`` names the per-user config counter file (ADR 0077
decision 15): a second writer of it, or a config write that skips it, would let a cached answer
outlive the user's write."""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROOTS = ("src", "apps", "libs", "scripts")
OWNER = "src/algotrade/storage/configs/generation.py"
WRITER = REPO / "src/algotrade/storage/configs/writer.py"


def test_nothing_but_the_generation_module_names_the_counter_file() -> None:
    hits = []
    for root in ROOTS:
        for path in (REPO / root).rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            text = path.read_text()
            if rel != OWNER and ('".generation' in text or "GENERATION_FILE" in text):
                hits.append(rel)
    assert not hits, f"only {OWNER} reads or writes the config generation file: {hits}"


def _public_methods(class_name: str) -> list[ast.FunctionDef]:
    tree = ast.parse(WRITER.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    return [n for n in cls.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def test_every_public_write_of_both_writers_runs_inside_the_generation() -> None:
    """A new ``FileConfigWriter`` / ``MemoryConfigWriter`` write without its generation
    decorator fails here."""
    wanted = {"FileConfigWriter": "_generation", "MemoryConfigWriter": "_memory_generation"}
    missing = []
    for class_name, decorator in wanted.items():
        for method in _public_methods(class_name):
            names = {d.id for d in method.decorator_list if isinstance(d, ast.Name)}
            writes = method.name.startswith(("save_", "add_", "discard_", "delete_", "archive_"))
            if writes and decorator not in names:
                missing.append(f"{class_name}.{method.name}")
    assert not missing, f"writes outside the generation seqlock: {missing}"
