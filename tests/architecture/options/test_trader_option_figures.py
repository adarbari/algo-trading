"""No raw vendor quote on a trader screen (decision B, plan docs/ui/evening-desk-plan.md section
7): a bid, ask, last or size never reaches a trader through the option grid, and no web operation
other than the admin-only raw Options tab reads an ``OptionQuote``. The grid's types carry only
derived figures (our mid, delta, IV, yield, breakeven, spread as a share of the mid, open
interest). The Options tab's operation is the one named below until the V6 web slice moves it
behind the admin guard; this list only shrinks."""

import json
import re
from pathlib import Path

import pytest
from graphql import (
    GraphQLNamedType,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLUnionType,
    TypeInfo,
    TypeInfoVisitor,
    Visitor,
    build_schema,
    get_named_type,
    parse,
    visit,
)

from tests.conftest import REPO_ROOT

SCHEMA = REPO_ROOT / "apps" / "api" / "schema.graphql"
GQL_TS = REPO_ROOT / "apps" / "web" / "src" / "shared" / "api" / "generated" / "graphql" / "gql.ts"
WEB_SRC = REPO_ROOT / "apps" / "web" / "src"
HAND_WRITTEN = re.compile(r"""[`'"]\s*((?:query|mutation)\s+\w+[^`'"]*)""")

# The names of a vendor's raw quote: what we compute from them (a mid, a spread share, an open
# interest, a delta) is a different name. ``volume`` is not here: the plan shows the day's volume.
FORBIDDEN = frozenset(
    {"bid", "ask", "last", "size", "bidSize", "askSize", "lastSize", "lastPrice", "quote", "quotes"}
)
RAW_QUOTE_TYPES = frozenset({"OptionQuote"})  # the stored contract quote, bid / ask / last
# Operations that read a raw quote today, admin-only in the V6 web PR. Shrink-only.
RAW_QUOTE_OPERATIONS = frozenset({"OptionQuotes"})


@pytest.fixture(scope="module")
def schema() -> GraphQLSchema:
    return build_schema(SCHEMA.read_text())


def _reachable(root: GraphQLNamedType) -> dict[str, GraphQLNamedType]:
    """Every object and union type reachable from ``root`` through fields and union members."""
    seen: dict[str, GraphQLNamedType] = {}
    todo = [root]
    while todo:
        found = todo.pop()
        if found.name in seen:
            continue
        if isinstance(found, GraphQLObjectType):
            seen[found.name] = found
            todo += [get_named_type(f.type) for f in found.fields.values()]
        elif isinstance(found, GraphQLUnionType):
            seen[found.name] = found
            todo += list(found.types)
    return seen


def test_the_option_grid_reaches_no_raw_quote_field(schema: GraphQLSchema) -> None:
    instrument = schema.type_map["Instrument"]
    assert isinstance(instrument, GraphQLObjectType)
    grid = get_named_type(instrument.fields["optionGrid"].type)
    assert grid is not None
    types = _reachable(grid)
    assert {"OptionGrid", "GridCell", "GridExpiry", "Unknown"} <= set(types)
    assert not set(types) & RAW_QUOTE_TYPES
    for name, found in types.items():
        fields = set(getattr(found, "fields", {}))
        assert not fields & FORBIDDEN, f"{name} carries a raw quote field: {fields & FORBIDDEN}"


def test_the_grid_cell_is_derived_figures_only(schema: GraphQLSchema) -> None:
    cell = schema.type_map["GridCell"]
    assert set(cell.fields) == {  # type: ignore[attr-defined]
        "band", "strike", "delta", "iv", "mid", "roc", "yieldAnn", "breakeven", "pBelow",
        "spreadPct", "openInterest",
    }  # fmt: skip


def _documents() -> dict[str, str]:
    """Every operation the web sends by name: the generated documents of gql.ts and the
    hand-written ``query <Name>`` template strings (tests and stories apart)."""
    found: dict[str, str] = {}
    for m in re.finditer(r'^\s+("(?:[^"\\]|\\.)*"): typeof', GQL_TS.read_text(), re.M):
        text = json.loads(m.group(1))
        head = re.search(r"\b(?:query|mutation)\s+(\w+)", text)
        if head:
            found[head.group(1)] = text
    for path in WEB_SRC.rglob("*.ts*"):
        if "generated" in path.parts or re.search(r"\.(test|stories)\.", path.name):
            continue
        for text in HAND_WRITTEN.findall(path.read_text()):
            head = re.search(r"\b(?:query|mutation)\s+(\w+)", text)
            if head:
                found.setdefault(head.group(1), text)
    return found


class _ReadsType(Visitor):
    """The type names the selected fields of a document belong to."""

    def __init__(self, info: TypeInfo) -> None:
        super().__init__()
        self.info = info
        self.parents: set[str] = set()

    def enter_field(self, *_: object) -> None:
        parent = self.info.get_parent_type()
        if parent is not None:
            self.parents.add(getattr(parent, "name", ""))


def _operations_reading(schema: GraphQLSchema, types: frozenset[str]) -> set[str]:
    out = set()
    for name, text in _documents().items():
        fragments = "\n".join(_documents().get(n, "") for n in re.findall(r"\.\.\.(\w+)", text))
        info = TypeInfo(schema)
        reads = _ReadsType(info)
        try:
            visit(parse(text + "\n" + fragments), TypeInfoVisitor(info, reads))
        except Exception:  # a fragment the parse cannot see: judged on the rest
            continue
        if reads.parents & types:
            out.add(name)
    return out


def test_only_the_admin_options_tab_reads_a_raw_quote(schema: GraphQLSchema) -> None:
    found = _operations_reading(schema, RAW_QUOTE_TYPES)
    assert found == RAW_QUOTE_OPERATIONS, (
        f"web operations reading a raw OptionQuote: {sorted(found)}; a trader screen shows "
        "derived figures only (Instrument.optionGrid). Shrink RAW_QUOTE_OPERATIONS, never grow it."
    )


def test_the_raw_quote_fields_are_confined_to_the_stored_quote_type(schema: GraphQLSchema) -> None:
    owners = {
        name
        for name, found in schema.type_map.items()
        if isinstance(found, GraphQLObjectType)
        and not name.startswith("__")
        and set(found.fields) & (FORBIDDEN - {"size", "quote", "quotes"})
    }
    assert owners == RAW_QUOTE_TYPES, owners


def test_the_forbidden_list_is_not_stale() -> None:
    assert Path(SCHEMA).is_file() and GQL_TS.is_file()
    assert set(_documents()) >= RAW_QUOTE_OPERATIONS
