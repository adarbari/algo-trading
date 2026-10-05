"""The read model's fitness tests (docs/api/read-model.md "Enforcement").

READ 3: GraphQL resolvers are thin (one loader or dataloader call, ``.of()`` wrapping, at most
a None guard). READ 7: every GraphQL object mirrors a read dataclass (its fields are the
dataclass's, mapped by one ``of()``). READ 9: no GraphQL type has a field named like a
catalogue feature (per-instrument values are read by name through ``features(names)``).

READ 2: only the read model's session plumbing picks or reads a session partition. Loaders
read a session-grain table through ``context.partition(ctx, table)`` for
``ctx.session.date`` (ADR 0036 decision 6): no
``StoreReader.table`` / ``require`` / ``table_range`` (a range read goes through ``data``'s
range functions with explicit dates), no ``dates`` / ``latest_date``, no ``snapshot``, no
``partition_for`` / ``latest_session`` / ``rollup_row`` / ``rollup_on`` of their own.

Scoped to every use case (``src/algotrade/services/**``) and the API (``apps/api/**``) since
read-model PR 10b deleted ``services/explore``; ``PARTITION_READERS`` names the few modules
that may, each with its reason (shrink-only: an entry that no longer reads is removed)."""

import ast
import dataclasses
import importlib
import inspect
import pkgutil
import typing

from algotrade.features.registry import FEATURES
from algotrade.services.features import site_features
from algotrade_api.graphql import types as graphql_types
from tests.conftest import REPO_ROOT

SERVICES = REPO_ROOT / "src" / "algotrade" / "services"
READ_MODEL = SERVICES / "read"
API = REPO_ROOT / "apps" / "api"
# The session plumbing: session.py resolves (and lists present / missing), context.py reads.
PLUMBING = {"session.py", "context.py"}
# Modules outside the read model that pick or read a partition, and why (never a page read).
PARTITION_READERS = {
    READ_MODEL / "session.py": "the session plumbing: resolves the session (ADR 0036)",
    READ_MODEL / "context.py": "the session plumbing: reads exactly the session's partition",
    SERVICES / "ondemand" / "screens.py": "a write: an on-request run targets the latest "
    "session (ADR 0033), outside read strictness (ADR 0036 decision 5)",
    SERVICES / "features.py": "run inputs: expression features over a date range the run "
    "names (screens, backtests); check_user_features (the validate-features CLI only) samples "
    "the latest date an input has: never a page read",
    SERVICES / "views.py": "run inputs: the FeatureView a screener evaluates, for the session "
    "the run names (missing data is an error, ADR 0008)",
    SERVICES / "datasets.py": "run inputs: the golden dataset catalogue the evaluation suite "
    "and the backtest CLI read",
}
PARTITION_READS = {
    "table", "require", "table_range", "dates", "latest_date", "snapshot", "read_snapshot",
    "partition_for", "latest_session", "rollup_row", "rollup_on",
}  # fmt: skip


def partition_reads(source: str) -> list[tuple[int, str]]:
    """``(line, callee)`` of every call in ``source`` that picks or reads a partition."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in PARTITION_READS:
                found.append((node.lineno, name))
    return sorted(found)


def test_only_loaders_read_partitions() -> None:
    sources = sorted([*SERVICES.rglob("*.py"), *API.rglob("*.py")])
    hits = [
        f"{path.relative_to(REPO_ROOT)}:{line} {name}()"
        for path in sources
        if path not in PARTITION_READERS
        for line, name in partition_reads(path.read_text())
    ]
    assert not hits, (
        f"[READ 2 / ADR 0036] a loader picks or reads a partition itself: {hits}. Read a "
        "session-grain table with services.read.context.partition(ctx, table) (UNKNOWN when "
        "absent); other grains by their one rule (.claude/skills/add-domain-object step 2)"
    )


# The context's inventory reads (what is stored, on dates the caller names): only the ops loader
# that reports on storage itself (the Admin completeness grid) calls or imports them.
INVENTORY_READS = {"stored_dates", "partition_on", "snapshot_on"}
INVENTORY_CALLERS = {READ_MODEL / "context.py", READ_MODEL / "ops" / "ingestion.py"}


def inventory_reads(source: str) -> list[tuple[int, str]]:
    """``(line, name)`` of every call to, or import of, an inventory read in ``source`` (an
    import catches an alias: ``from ...context import partition_on as p``)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in INVENTORY_READS:
                found.append((node.lineno, name))
        elif isinstance(node, ast.ImportFrom):
            found += [(node.lineno, a.name) for a in node.names if a.name in INVENTORY_READS]
    return sorted(found)


def test_inventory_reads_only_in_the_completeness_loader() -> None:
    sources = [*REPO_ROOT.joinpath("src").rglob("*.py"), *REPO_ROOT.joinpath("apps").rglob("*.py")]
    hits = [
        f"{path.relative_to(REPO_ROOT)}:{line} {name}"
        for path in sorted(sources)
        if path not in INVENTORY_CALLERS
        for line, name in inventory_reads(path.read_text())
    ]
    assert not hits, (
        f"[READ 2 / ADR 0036] inventory reads outside services/read/ops/ingestion.py: {hits}. "
        "They report what is stored on dates the caller names (the Admin completeness grid); a "
        "fact for the session is read with services.read.context.partition(ctx, table)"
    )


def test_the_inventory_check_catches_an_alias() -> None:
    aliased = (
        "from algotrade.services.read.context import partition_on as p\n"
        "def load(ctx):\n"
        "    return p(ctx, 't', ctx.session.date)\n"
    )
    assert inventory_reads(aliased) == [(1, "partition_on")]


def test_the_plumbing_exists() -> None:
    assert {p.name for p in READ_MODEL.glob("*.py")} >= PLUMBING


def test_every_partition_reader_still_reads() -> None:
    """Shrink-only: an allowed module that no longer picks or reads a partition leaves the set."""
    idle = [
        str(path.relative_to(REPO_ROOT))
        for path in PARTITION_READERS
        if not path.exists() or not partition_reads(path.read_text())
    ]
    assert not idle, f"remove these from PARTITION_READERS (they read no partition): {idle}"


def test_the_check_catches_a_loader_reading_a_partition() -> None:
    loader = (
        "def load(ctx):\n"
        "    day = ctx.reader.latest_date('rollups/instrument/x@v1')\n"
        "    return ctx.reader.table('rollups/instrument/x@v1', day), snapshot(ctx.reader, 'x')\n"
    )
    assert partition_reads(loader) == [(2, "latest_date"), (3, "snapshot"), (3, "table")]
    assert partition_reads("def load(ctx):\n    return partition(ctx, 't')\n") == []


# ---------------------------------------------------------------------------- READ 3
GRAPHQL = REPO_ROOT / "apps" / "api" / "algotrade_api" / "graphql"
LOADER_METHODS = {"load", "load_many"}


def _is_field(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in node.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        if isinstance(target, ast.Attribute) and target.attr == "field":
            return True
    return False


def _is_none_guard(test: ast.expr) -> bool:
    if isinstance(test, ast.BoolOp):
        return all(_is_none_guard(v) for v in test.values)
    return (
        isinstance(test, ast.Compare)
        and all(isinstance(op, ast.Is | ast.IsNot) for op in test.ops)
        and all(isinstance(c, ast.Constant) and c.value is None for c in test.comparators)
    )


def _is_of(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "of"
    )


def resolver_problems(source: str) -> list[str]:
    """What makes the resolvers in ``source`` more than thin, ``"<name>: <why>"``."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or not _is_field(node):
            continue
        loads = 0
        for inner in ast.walk(node):
            if isinstance(inner, ast.For | ast.AsyncFor | ast.While | ast.If | ast.Try | ast.With):
                found.append(f"{node.name}: a {type(inner).__name__.lower()} statement")
            elif isinstance(inner, ast.IfExp) and not _is_none_guard(inner.test):
                found.append(f"{node.name}: a condition on a value (only `is None` guards)")
            elif isinstance(inner, ast.ListComp | ast.GeneratorExp | ast.SetComp | ast.DictComp):
                if not (isinstance(inner, ast.ListComp) and _is_of(inner.elt)):
                    found.append(f"{node.name}: a comprehension that does more than `.of()`")
            elif isinstance(inner, ast.Call):
                func = inner.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                loads += name.startswith("load_") or name in LOADER_METHODS
        if loads > 1:
            found.append(
                f"{node.name}: {loads} loader calls (one loader or dataloader per resolver)"
            )
    return found


def test_resolvers_call_one_loader() -> None:
    sources = sorted((GRAPHQL / "types").rglob("*.py"))
    hits = [
        f"{path.relative_to(REPO_ROOT)}: {problem}"
        for path in sources
        for problem in resolver_problems(path.read_text())
    ]
    assert not hits, (
        f"[READ 3 / ADR 0037] resolvers with logic: {hits}. A resolver reads info.context, "
        "calls one loader (services/read) or one dataloader .load(), and wraps the result with "
        ".of(); the logic is a loader first (.claude/skills/add-graphql-field step 3-4)"
    )


def test_the_resolver_check_catches_logic() -> None:
    thick = (
        "@strawberry.field\n"
        "def f(self, info):\n"
        "    rows = load_a(info.context)\n"
        "    for r in rows:\n"
        "        pass\n"
        "    return [r.x for r in rows] if rows else load_b(info.context)\n"
    )
    assert resolver_problems(thick) == [
        "f: a for statement",
        "f: a condition on a value (only `is None` guards)",
        "f: a comprehension that does more than `.of()`",
        "f: 2 loader calls (one loader or dataloader per resolver)",
    ]
    thin = (
        "@strawberry.field(description='x')\n"
        "async def f(self, info):\n"
        "    found = await self.ctx.loaders.x.load(1)\n"
        "    return [X.of(v) for v in found] if found is not None else None\n"
    )
    assert resolver_problems(thin) == []


# ---------------------------------------------------------------------------- READ 7 / READ 9
def graphql_objects() -> list[type]:
    """Every Strawberry object type declared in ``algotrade_api.graphql.types``."""
    found = []
    for info in pkgutil.walk_packages(graphql_types.__path__, graphql_types.__name__ + "."):
        module = importlib.import_module(info.name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            definition = getattr(cls, "__strawberry_definition__", None)
            if cls.__module__ == module.__name__ and definition is not None:
                found.append(cls)
    return found


def test_the_type_walk_reaches_every_area() -> None:
    """``types/`` is split by area (``instruments/``, ``screens/``, ``ops/``): the checks see
    them all."""
    names = {cls.__name__ for cls in graphql_objects()}
    areas = {"Instrument", "FeatureValue", "Ideas", "Screener", "ScreenDetail", "Backtest"}
    assert {"Query", "Session"} | areas <= names


def test_types_mirror_read_model() -> None:
    problems = []
    objects = graphql_objects()
    assert objects, "no GraphQL object types found"
    for cls in objects:
        if cls.__name__ == "Query":  # the root: fields only, each a resolver
            assert all(f.base_resolver for f in cls.__strawberry_definition__.fields)
            continue
        of = cls.__dict__.get("of")
        if not isinstance(of, classmethod):
            problems.append(f"{cls.__name__}: no of() classmethod (the one mapping)")
            continue
        source = typing.get_type_hints(of.__func__).get("d")
        if source is None or not dataclasses.is_dataclass(source):
            problems.append(f"{cls.__name__}.of(d): d is not a services.read dataclass")
            continue
        if not source.__module__.startswith("algotrade.services.read."):
            problems.append(f"{cls.__name__}.of(d): {source.__module__} is not the read model")
        mirrored = {f.name for f in dataclasses.fields(source)}
        for field in cls.__strawberry_definition__.fields:
            if field.base_resolver is None and field.python_name not in mirrored:
                problems.append(
                    f"{cls.__name__}.{field.python_name}: not a field of {source.__name__}"
                )
    assert not problems, (
        f"[READ 7 / ADR 0037] GraphQL types that do not mirror a read dataclass: {problems}. "
        "Copy the fields from the services/read dataclass and map them in one of(); anything "
        "else is a resolver over a loader (.claude/skills/add-graphql-field step 4)"
    )


# Fields of range-grain types that share a catalogue column's name but are not a session's
# fact (the REST twin keeps the same entry in TYPED_FACT_FIELDS). Shrink-only, never a value.
RANGE_GRAIN_FIELDS = {
    "PriceBar.close": "a bar of a price series (range grain, docs/api/read-model.md); the "
    "session's close as a fact is rollup.price_stats@v2.close",
}


def test_no_typed_feature_fields() -> None:
    """Identity (``symbol``, ``name``, ``exchange``, ...) is typed by rule (ADR 0038); a field
    named like a rollup column or an expression feature is a per-instrument value."""
    catalogue = {f.name for f in FEATURES.values()} | set(site_features().expressions)
    named = {
        f"{cls.__name__}.{field.python_name}"
        for cls in graphql_objects()
        for field in cls.__strawberry_definition__.fields
        if field.python_name in catalogue
    }
    hits = sorted(named - RANGE_GRAIN_FIELDS.keys())
    gone = sorted(RANGE_GRAIN_FIELDS.keys() - named)
    assert not gone, f"remove these retired entries from RANGE_GRAIN_FIELDS: {gone}"
    assert not hits, (
        f"[READ 9 / ADR 0038] GraphQL fields named like catalogue features: {hits}. Read "
        "per-instrument values by name through `features(names)` (docs/api/read-model.md "
        "'Catalogue feature or typed field'); never a typed field"
    )


def test_type_ignores_only_on_strawberry_field_decorators() -> None:
    """Strawberry's ``@strawberry.field(...)`` is untyped under mypy strict even with its
    plugin; that one ignore is allowed on that decorator in ``graphql/types/`` and nowhere
    else in the GraphQL layer (docs/api/read-model.md "Risks and tough calls")."""
    hits = []
    for path in sorted(GRAPHQL.rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if "type: ignore" not in line:
                continue
            allowed = (
                "types" in path.relative_to(GRAPHQL).parts
                and line.strip() == "@strawberry.field(  # type: ignore[untyped-decorator]"
            )
            if not allowed:
                hits.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not hits, f"type: ignore outside the strawberry.field decorators of types/: {hits}"
