"""Guide coverage (ADR 0051, enforced here): what a reader meets in the app is explained by
a Guide entry, and what the web code refers to exists. The declared mapping is
``architecture/guide_coverage.toml``; the Guide's entries are ``guide_entries`` (the one list of
every kind, as ``test_start.py`` reads it). Four checks:

1. every GraphQL enum, and every String field named like a status / state / kind / trigger /
   label / verdict, maps each of its values to a Guide entry, or is exempt with a reason;
2. every section of ``workspaces.ts`` has a Start here page or is exempt, and every top-level
   route belongs to a section;
3. every titled container (a design-system component with ``title`` and ``actions``) carries
   a help button, per file, against a shrink-only baseline;
4. every Guide reference written in ``apps/web/src`` resolves to an entry.

Baselines only shrink: an item that becomes covered fails until its line is removed."""

import fnmatch
import importlib
import re
import tomllib
from enum import Enum
from pathlib import Path
from typing import Any

import graphql
import pytest

from algotrade.config.edges.sides import SIDES
from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.config.site.guide.start import ENTRY_KINDS
from algotrade.config.user import SITE_USER, UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import StoreContext, open_stores
from algotrade.services.read.guide.search import guide_entries
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT

COVERAGE_FILE = "architecture/guide_coverage.toml"
FIX = (
    f"cover it with a Guide entry and map it in {COVERAGE_FILE} "
    "(`.claude/skills/add-guide-content`)"
)
WEB = REPO_ROOT / "apps" / "web"
STATUS_LIKE = re.compile("status|state|kind|trigger|label|verdict", re.I)
NOT_SOURCE = ("*.test.ts*", "*.stories.ts*", "*.d.ts")
REF_KINDS = ("term", "start", "indicator", "episode", "playbook", "situation")  # fields are dynamic


# ------------------------------------------------------------------ scanners (unit-tested below)


def _skip_braces(text: str, start: int) -> int:
    """The index after the ``{...}`` that opens at ``start`` (a string literal on one line, or a
    template literal, may hold braces; a lone apostrophe in JSX text is not a string)."""
    depth, i = 0, start
    while i < len(text):
        c = text[i]
        if c in "'\"":
            end = text.find(c, i + 1)
            if end != -1 and "\n" not in text[i:end]:
                i = end
        elif c == "`":
            i = text.find("`", i + 1)
            if i == -1:
                return len(text)
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _attributes(text: str, i: int) -> dict[str, str]:
    """The attributes of the JSX tag whose name ends at ``i``: name -> value text (a string's
    contents or a ``{...}`` expression's), read up to the tag's own ``>`` (not the ``>`` of an
    arrow function or of JSX inside a ``{}``)."""
    attrs: dict[str, str] = {}
    while i < len(text) and text[i] != ">" and text[i : i + 2] != "/>":
        if text[i] == "{":  # a spread
            i = _skip_braces(text, i)
        elif match := re.compile(r"[\w:-]+").match(text, i):
            name, i = match.group(0), match.end()
            attrs[name] = ""
            if text[i : i + 1] == "=":
                i += 1
                if text[i : i + 1] in ("'", '"'):
                    end = text.index(text[i], i + 1)
                    attrs[name], i = text[i + 1 : end], end + 1
                elif text[i : i + 1] == "{":
                    end = _skip_braces(text, i)
                    attrs[name], i = text[i + 1 : end - 1], end
        else:
            i += 1
    return attrs


def jsx_tags(text: str, names: tuple[str, ...]) -> list[tuple[str, dict[str, str]]]:
    """Every JSX opening tag named one of ``names`` in ``text``, with its attributes."""
    opening = re.compile(r"<(" + "|".join(names) + r")(?=[\s/>])")
    return [(m.group(1), _attributes(text, m.end())) for m in opening.finditer(text)]


_HELP_CALL = r"\b(?:help|termHelp)\(\s*"
_LITERAL_REF = re.compile(
    r"kind:\s*'(" + "|".join(REF_KINDS) + r")',\s*id:\s*'([^']+)'"
    r"|" + _HELP_CALL + r"'([^']+)'\s*\)|\bhelp=\"([a-z_]+)\""
)
_TEMPLATE_REF = re.compile(_HELP_CALL + r"`([^`]*\$\{[^`]*)`\s*\)")


def literal_refs(text: str) -> list[str]:
    """Every Guide reference written out in ``text`` as ``kind:id``: an entry object with a
    literal id, a ``help('id')`` / ``termHelp('id')`` call or a ``help="id"`` prop (terms)."""
    refs = []
    for m in _LITERAL_REF.finditer(text):
        kind, ident, call, prop = m.groups()
        refs.append(f"{kind}:{ident}" if kind else f"term:{call or prop}")
    return refs


def template_refs(text: str) -> list[str]:
    """The ``help(`...${x}`)`` templates in ``text`` (their ids are declared ``dynamic_ref``)."""
    return _TEMPLATE_REF.findall(text)


def has_help(actions: str, uses_help_context: bool) -> bool:
    """Whether an ``actions`` expression carries a Guide button: a ``GuideHelp`` element, the
    one exported ``termHelp`` helper, or (in a file that reads the edge builder's context with
    ``useHelp``) its ``help(`` call."""
    return bool(re.search(r"\bGuideHelp\b|\btermHelp\(", actions)) or (
        uses_help_context and bool(re.search(r"\bhelp\(", actions))
    )


def web_sources(root: Path) -> list[Path]:
    """Every non-test, non-story, non-generated ``.ts`` / ``.tsx`` file under ``root``."""
    return [
        p
        for p in sorted(root.rglob("*.ts*"))
        if p.suffix in (".ts", ".tsx")
        and "generated" not in p.parts
        and not any(fnmatch.fnmatchcase(p.name, skip) for skip in NOT_SOURCE)
    ]


def uncovered_titled(text: str, tags: tuple[str, ...]) -> int:
    """Titled containers of ``tags`` in one source whose ``actions`` (or ``info``, the slot a
    read-only ConditionGroup shows) carry no help button."""
    context = bool(re.search(r"import\s*\{[^}]*\buseHelp\b[^}]*\}\s*from", text))
    return sum(
        1
        for _, attrs in jsx_tags(text, tags)
        if "title" in attrs
        and not has_help(attrs.get("actions", "") + " " + attrs.get("info", ""), context)
    )


def schema_sources(text: str) -> dict[str, tuple[str, ...] | None]:
    """The coverage subjects of a GraphQL schema: ``graphql:Enum`` -> its values and
    ``graphql:Type.field`` -> None for every String field named like a status."""
    schema = graphql.build_schema(text)
    found: dict[str, tuple[str, ...] | None] = {}
    for name, kind in schema.type_map.items():
        if name.startswith("__"):
            continue
        if isinstance(kind, graphql.GraphQLEnumType):
            found[f"graphql:{name}"] = tuple(kind.values)
        elif isinstance(kind, (graphql.GraphQLObjectType, graphql.GraphQLInterfaceType)):
            for field, definition in kind.fields.items():
                if graphql.get_named_type(definition.type).name == "String" and STATUS_LIKE.search(
                    field
                ):
                    found[f"graphql:{name}.{field}"] = None
    return found


def python_values(source: str) -> set[str]:
    """The values of a ``python:<module>:<NAME>`` source: a tuple / set of str or an Enum."""
    _, module, name = source.split(":")
    value = getattr(importlib.import_module(module), name)
    if isinstance(value, type) and issubclass(value, Enum):
        return {str(m.value) for m in value}
    assert all(isinstance(v, str) for v in value), f"{source} is not a collection of str"
    return set(value)


def route_paths(routes: Path) -> set[str]:
    """The top-level route paths under ``app/routes/{trader,admin}``: a route whose parent is
    its workspace layout (a sub-route such as ``edges/new`` belongs to its first segment)."""
    found = set()
    for workspace, prefix in (("trader", "/"), ("admin", "/admin/")):
        for path in web_sources(routes / workspace):
            text = path.read_text()
            for m in re.finditer(
                r"getParentRoute:\s*\(\)\s*=>\s*(?:traderRoute|adminRoute|parent)\b[^}]*?"
                r"path:\s*'([^']+)'",
                text,
            ):
                first = m.group(1).split("/")[0]
                if not first.startswith("$"):
                    found.add(prefix + first)
            found |= set(re.findall(r"placeholderRoute\([^,]+,[^,]+,\s*'(/[^']+)'", text))
    return found


def section_paths(text: str) -> list[str]:
    """The ``path`` of every section in ``workspaces.ts``."""
    return re.findall(r"path:\s*'(/[^']*)'", text)


# ------------------------------------------------------------------ the declared mapping


@pytest.fixture(scope="module")
def coverage() -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / COVERAGE_FILE).read_text())


@pytest.fixture(scope="module")
def entries() -> set[str]:
    site: StoreContext = open_stores(
        StoreReader(MemoryBackend()), FileConfigStore(REPO_ROOT / "config"), UserContext(SITE_USER)
    )
    return {f"{e.kind}:{e.id}" for e in guide_entries(site)}


@pytest.fixture(scope="module")
def sources() -> dict[str, tuple[str, ...] | None]:
    return schema_sources((REPO_ROOT / "apps/api/schema.graphql").read_text())


def test_every_outcome_side_has_a_guide_term(entries: set[str]) -> None:
    """``EdgeVerdict.side`` is shown beside the basis (a chip for a side other than ``long``) and
    is not named like a status, so ``STATUS_LIKE`` does not find it: each value of ``SIDES`` is
    a term ``side_<value>`` here instead (ADR 0053 amendment, outcome sides)."""
    missing = [f"side_{v}" for v in SIDES if f"term:side_{v}" not in entries]
    assert not missing, f"no Guide term for the outcome side(s) {missing}; {FIX}"


def assert_pinned(coverage: dict[str, Any], name: str, size: int) -> None:
    """A baseline only shrinks: its size equals the pin ``max_<name>``, which a PR only lowers
    (adding to a baseline fails here; raising the pin shows in review)."""
    pin = coverage["baseline"][f"max_{name}"]
    assert size <= pin, f"{COVERAGE_FILE}: [baseline] {name} grew to {size} (pin {pin}); {FIX}"
    assert size == pin, (
        f"{COVERAGE_FILE}: [baseline] {name} shrank to {size}: set max_{name} = {size}"
    )


def unresolved(refs: list[str], entries: set[str]) -> list[str]:
    return [r for r in refs if r not in entries]


# 1. enums and status-like fields


def test_every_enum_and_status_field_is_declared_or_baselined(
    coverage: dict[str, Any], sources: dict[str, Any]
) -> None:
    declared = {e["source"] for e in coverage["enum"]}
    baseline = set(coverage["baseline"]["enums"])
    new = sorted(set(sources) - declared - baseline)
    assert not new, f"{COVERAGE_FILE}: no Guide coverage for {new}; {FIX}"
    gone = sorted((declared | baseline) - set(sources))
    assert not gone, f"{COVERAGE_FILE}: declared or baselined but not in the schema: {gone}"
    covered = sorted(baseline & declared)
    assert not covered, f"{COVERAGE_FILE}: covered now, remove from [baseline] enums: {covered}"
    assert_pinned(coverage, "enums", len(baseline))


def test_each_declared_enum_is_exempt_with_a_reason_or_maps_every_value(
    coverage: dict[str, Any], sources: dict[str, Any], entries: set[str]
) -> None:
    problems = []
    for entry in coverage["enum"]:
        source = entry["source"]
        if "exempt" in entry:
            if not str(entry["exempt"]).strip() or {"values", "values_from", "names"} & set(entry):
                problems.append(f"{source}: `exempt` takes a reason and no `values` / `names`")
            continue
        values = entry.get("values", {})
        if "values_from" in entry:
            expected = python_values(entry["values_from"])
        elif sources.get(source) is not None:
            expected = set(sources[source])
        else:
            problems.append(
                f"{source}: a String field needs `values_from = python:<module>:<NAME>`"
            )
            continue
        if set(values) != expected:
            problems.append(
                f"{source}: values differ from the source: missing "
                f"{sorted(expected - set(values))}, unknown {sorted(set(values) - expected)}"
            )
        problems += [
            f"{source}.{v}: {ref} is no Guide entry"
            for v, ref in values.items()
            if ref not in entries
        ]
    assert not problems, f"{COVERAGE_FILE}:\n" + "\n".join(problems) + f"\n{FIX}"


def test_a_term_shared_by_several_values_names_each_of_them(coverage: dict[str, Any]) -> None:
    """Values may share one term only as Stripe's lifecycle tables do: the term says each value
    (its words, ``_`` read as a space, or the label the app shows, ``names``) and what it
    means; a generic term fails."""
    glossary = {
        t.id: f"{t.term} {t.short} {t.body}".lower()
        for t in load_guide_glossary(FileConfigStore(REPO_ROOT / "config")).terms
    }
    problems = []
    for entry in coverage["enum"]:
        names: dict[str, str] = entry.get("names", {})
        if stray := sorted(set(names) - set(entry.get("values", {}))):
            problems.append(f"{entry['source']}: `names` for values it does not map: {stray}")
        shared: dict[str, list[str]] = {}
        for value, ref in entry.get("values", {}).items():
            shared.setdefault(ref, []).append(value)
        for ref, values in shared.items():
            kind, _, term_id = ref.partition(":")
            if len(values) < 2 or (term_id not in glossary and kind == "term"):
                continue  # one value, or a term the resolve check already fails
            if kind != "term":
                problems.append(f"{entry['source']}: {values} share {ref}; only a term is shared")
                continue
            words = re.findall(r"[a-z]+", glossary[term_id])
            problems += [
                f"{entry['source']}.{v}: {ref} does not name it"
                for v in values
                if not set(re.findall(r"[a-z]+", names.get(v, v.replace("_", " ")).lower()))
                <= set(words)
            ]
    assert not problems, (
        f"{COVERAGE_FILE}: a shared term must name each value it explains (or give the value "
        "its own [[term]] in config/site/guide/glossary/<theme>.toml):\n" + "\n".join(problems)
    )


# 2. sections and routes


def test_every_section_has_a_start_page_or_is_exempt(
    coverage: dict[str, Any], entries: set[str]
) -> None:
    workspace = {*section_paths((WEB / "src/app/workspaces/workspaces.ts").read_text())}
    declared = {s["path"] for s in coverage["section"]}
    baseline = set(coverage["baseline"]["sections"])
    new = sorted(workspace - declared - baseline)
    assert not new, f"{COVERAGE_FILE}: a section with no Start here page: {new}; {FIX}"
    gone = sorted((declared | baseline) - workspace)
    assert not gone, f"{COVERAGE_FILE}: not a section of workspaces.ts any more: {gone}"
    covered = sorted(baseline & declared)
    assert not covered, f"{COVERAGE_FILE}: covered now, remove from [baseline] sections: {covered}"
    assert_pinned(coverage, "sections", len(baseline))
    for s in coverage["section"]:
        if "exempt" in s:
            assert str(s["exempt"]).strip() and "start" not in s, f"{s['path']}: reason or start"
        else:
            assert s["start"].startswith("start:"), f"{s['path']}: a Start here page (start:<id>)"
            assert s["start"] in entries, f"{s['path']}: {s['start']} is no Start here page"


def test_every_top_level_route_belongs_to_a_section(coverage: dict[str, Any]) -> None:
    workspace = set(section_paths((WEB / "src/app/workspaces/workspaces.ts").read_text()))
    routes = route_paths(WEB / "src/app/routes")
    stray = sorted(routes - workspace - set(coverage["non_sections"]))
    assert not stray, (
        f"{COVERAGE_FILE}: a route that is no section of workspaces.ts: {stray} "
        "(add the section, or list it under non_sections with its reason)"
    )
    assert not set(coverage["non_sections"]) & workspace, "non_sections lists a section"
    unseen = sorted(workspace - routes)
    assert not unseen, f"route_paths found no route for sections {unseen}: fix the scanner"


# 3. titled containers


def test_panel_tags_are_the_components_with_title_and_actions(coverage: dict[str, Any]) -> None:
    found = {
        p.stem
        for p in web_sources(WEB / "design-system/components")
        if re.search(r"^\s+title\??:", p.read_text(), re.M)
        and re.search(r"^\s+actions\??:", p.read_text(), re.M)
    }
    assert found == set(coverage["panels"]["tags"]), (
        f"{COVERAGE_FILE} [panels] tags must be every design-system component with a `title` "
        f"and `actions` prop: {sorted(found)}"
    )


def test_titled_containers_carry_help_against_the_baseline(coverage: dict[str, Any]) -> None:
    tags = tuple(coverage["panels"]["tags"])
    baseline: dict[str, int] = coverage["baseline"]["panels"]
    counts = {}
    for path in web_sources(WEB / "src"):
        if n := uncovered_titled(path.read_text(), tags):
            counts[path.relative_to(WEB).as_posix()] = n
    over = [
        f"{f}: {n} (baseline {baseline.get(f, 0)})"
        for f, n in counts.items()
        if n > baseline.get(f, 0)
    ]
    assert not over, (
        f"a titled container without a help button; add `actions={{termHelp('<term>')}}` "
        f"(or a GuideHelp) and cover it in the Guide ({COVERAGE_FILE}, "
        f"`.claude/skills/add-guide-content`):\n" + "\n".join(over)
    )
    under = [
        f"{f}: {counts.get(f, 0)} (baseline {n})"
        for f, n in baseline.items()
        if counts.get(f, 0) < n
    ]
    assert not under, f"{COVERAGE_FILE}: lower [baseline.panels]:\n" + "\n".join(under)
    assert_pinned(coverage, "panels", sum(baseline.values()))


# 4. references


def test_every_guide_reference_in_the_web_code_resolves(
    coverage: dict[str, Any], entries: set[str]
) -> None:
    dynamic = {(d["file"], d["template"]): d for d in coverage["dynamic_ref"]}
    seen_templates = set()
    problems = []
    for path in web_sources(WEB / "src"):
        text, rel = path.read_text(), path.relative_to(WEB).as_posix()
        problems += [
            f"{rel}: {r} is no Guide entry" for r in unresolved(literal_refs(text), entries)
        ]
        for template in template_refs(text):
            seen_templates.add((rel, template))
            if (rel, template) not in dynamic:
                problems.append(f"{rel}: `{template}` needs a [[dynamic_ref]] listing its ids")
    for key, d in dynamic.items():
        if key not in seen_templates:
            problems.append(f"{key[0]}: [[dynamic_ref]] `{key[1]}` is not in the file any more")
        problems += [
            f"{key[0]}: {d['kind']}:{i} is no Guide entry"
            for i in d["ids"]
            if f"{d['kind']}:{i}" not in entries
        ]
    assert not problems, f"Guide references that do not resolve ({FIX}):\n" + "\n".join(problems)


def test_entry_kinds_cover_the_reference_kinds() -> None:
    assert set(REF_KINDS) <= set(ENTRY_KINDS)


# ------------------------------------------------------------------ the scanners themselves


def test_a_tag_ends_at_its_own_close_not_at_an_arrow_or_nested_jsx() -> None:
    src = (
        '<Panel title="A" actions={items.map((x) => <Tip a="b>c">{x}</Tip>)} dense>\n'
        "  <Panel title='inner'/>\n</Panel>"
    )
    (outer, a), (_, b) = jsx_tags(src, ("Panel",))
    assert outer == "Panel" and a["title"] == "A" and "map" in a["actions"] and "dense" in a
    assert b == {"title": "inner"}


def test_a_title_inside_a_string_or_a_child_is_not_the_tags_attribute() -> None:
    src = "<Panel actions={<GuideHelp entry={{ kind: 'term', id: 'x' }} title='t' />}>"
    ((_, attrs),) = jsx_tags(src, ("Panel",))
    assert set(attrs) == {"actions"}
    assert jsx_tags("<PanelHeader title='x' />", ("Panel",)) == []


def test_help_is_recognised_only_as_the_guide_button() -> None:
    assert has_help("<GuideHelp entry={e} />", False)
    assert has_help("termHelp('lift')", False)
    assert not has_help("<Button>Help</Button>", False)
    assert not has_help("help('lift')", False)
    assert has_help("help('lift')", True)


def test_uncovered_titled_counts_only_titled_tags_without_help() -> None:
    src = (
        "<Panel title='a'>x</Panel><Panel>y</Panel>"
        "<Panel title='b' actions={termHelp('lift')}>z</Panel>"
        "<Banner title={t}>q</Banner>"
    )
    assert uncovered_titled(src, ("Panel", "Banner")) == 2


def test_references_are_extracted_in_every_written_form() -> None:
    src = (
        "<GuideHelp entry={{ kind: 'term', id: 'regime' }} /> {help('lift')} "
        "termHelp( 'edge_status' ) <Labelled help=\"win_rate\" /> "
        "entry={{ kind: 'field', id: name }} {help(`edge_builder_${step}`)}"
    )
    assert literal_refs(src) == ["term:regime", "term:lift", "term:edge_status", "term:win_rate"]
    assert template_refs(src) == ["edge_builder_${step}"]


def test_a_schema_yields_enums_and_status_like_string_fields() -> None:
    text = "type Query { a: A } enum Color { RED } type A { status: String! n: Int labels: [String!]! }"  # noqa: E501
    assert schema_sources(text) == {
        "graphql:Color": ("RED",),
        "graphql:A.status": None,
        "graphql:A.labels": None,
    }


def test_section_and_route_paths_are_read_from_the_sources(tmp_path: Path) -> None:
    assert section_paths("{ path: '/a', label: 'A' }, { path: '/admin/b' }") == ["/a", "/admin/b"]
    (tmp_path / "trader").mkdir()
    (tmp_path / "admin").mkdir()
    (tmp_path / "trader" / "r.tsx").write_text(
        "createRoute({ getParentRoute: () => traderRoute, path: 'edges/$id/edit' });\n"
        "createRoute({ getParentRoute: () => screenersRoute, path: 'new' });\n"
        "placeholderRoute(traderRoute, TRADER, '/backtests', 'backtests');\n"
    )
    (tmp_path / "admin" / "i.tsx").write_text(
        "createRoute({\n  getParentRoute: () => parent,\n  path: 'ingestion',\n});\n"
    )
    assert route_paths(tmp_path) == {"/edges", "/backtests", "/admin/ingestion"}
