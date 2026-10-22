"""`scripts/perf/web_page_ops.py`: route enumeration, the static page -> operation walk and the
capture matching, on small fixture trees (no real web source)."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "perf" / "web_page_ops.py"
_spec = importlib.util.spec_from_file_location("perf_web_page_ops", SCRIPT)
assert _spec and _spec.loader
wpo = importlib.util.module_from_spec(_spec)
sys.modules["perf_web_page_ops"] = wpo
_spec.loader.exec_module(wpo)

FILES = {
    "app/routes/root.ts": "export const rootRoute = createRootRoute({});",
    "app/routes/trader.tsx": """
export const traderRoute = createRoute({ getParentRoute: () => rootRoute, id: 'trader' });
const ListPage = lazyPage(() => import('@/pages/list'), 'ListPage');
const ItemPage = lazyPage(() => import('@/pages/item'), 'ItemPage');
function ItemRoute() {
  return <ItemPage id="x" />;
}
const listRoute = createRoute({
  getParentRoute: () => itemsRoute,
  path: '/',
  ...pageRoute(ListPage, (page, client) => {
    page.prefetchListReads(client);
  }),
  component: ListPage,
});
export const itemsRoute = createRoute({ getParentRoute: () => traderRoute, path: 'items' });
const itemRoute = createRoute({
  getParentRoute: () => itemsRoute,
  path: '$id',
  validateSearch: (s) => s,
  component: ItemRoute,
});
export const tree = itemsRoute.addChildren([listRoute, itemRoute]);
placeholderRoute(traderRoute, TRADER, '/later', 'later');
""",
    "pages/list/index.ts": "export { ListPage, prefetchListReads } from './ui/ListPage';",
    "pages/list/ui/ListPage.tsx": """
import { useRows, useDetail } from '@/entities/rows';
export function ListPage() {
  const rows = useRows();
  const [open, setOpen] = useState(false);
  return <div onClick={() => useDetail()}>{open && <Drawer />}{rows}</div>;
}
function Drawer() {
  const d = useDetail();
  return d;
}
export function prefetchListReads(client) {
  client.ensureQueryData(RowsDoc);
}
""",
    "pages/item/index.ts": "export { ItemPage } from './ItemPage';",
    "pages/item/ItemPage.tsx": "export function ItemPage() { return null; }",
    "entities/rows/index.ts": "export { useRows, useDetail } from './api/hooks';",
    "entities/rows/api/hooks.ts": """
const RowsDoc = graphql(`
  query Rows { rows { id } }
`);
const DetailDoc = graphql(`
  query Detail { detail { id } }
`);
const SaveDoc = graphql(`
  mutation Save { save { id } }
`);
export function useRows() {
  return useQuery({ queryFn: () => gql(RowsDoc) });
}
export function useDetail() {
  return useQuery({ queryFn: () => gql(DetailDoc), enabled: true });
}
export function useSave() {
  return gql(SaveDoc);
}
""",
}


def tree(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    return tmp_path


def test_enumerate_routes_builds_full_paths_and_skips_layouts(tmp_path: Path) -> None:
    routes = wpo.enumerate_routes(tree(tmp_path))
    by_path = {r.path: r for r in routes}
    assert set(by_path) == {"/items", "/items/$id", "/later"}  # trader / items are layouts
    assert by_path["/items/$id"].search is True
    assert by_path["/later"].kind == "placeholder"
    assert by_path["/items"].pages[0][1] == "ListPage"


def test_page_component_behind_a_local_wrapper_is_resolved(tmp_path: Path) -> None:
    routes = {r.path: r for r in wpo.enumerate_routes(tree(tmp_path))}
    assert [n[1] for n in routes["/items/$id"].pages] == ["ItemPage"]
    assert [n[1] for n in routes["/items"].prefetch] == ["prefetchListReads"]


def test_static_walk_classes_on_load_interaction_and_ignores_mutations(tmp_path: Path) -> None:
    src = tree(tmp_path)
    routes = wpo.enumerate_routes(src)
    pages, shell = wpo.static_page_ops(src, routes)
    ops = pages["/items"]
    assert ops["Rows"] == wpo.LOAD
    # Detail: only inside a handler (`onClick`) and behind `open &&`; the best path is the
    # conditional drawer, and the hook gates itself with `enabled`: uncertain, not on-load
    assert ops["Detail"] == wpo.MAYBE
    assert "Save" not in ops
    assert shell == {}
    assert pages["/items/$id"] == {}


def test_handler_only_reference_is_interaction(tmp_path: Path) -> None:
    src = tree(tmp_path)
    page = src / "pages/list/ui/ListPage.tsx"
    page.write_text(page.read_text().replace("{open && <Drawer />}", ""))
    routes = wpo.enumerate_routes(src)
    pages, _ = wpo.static_page_ops(src, routes)
    assert pages["/items"]["Detail"] == wpo.HANDLER


def test_all_query_ops_lists_queries_only(tmp_path: Path) -> None:
    assert wpo.all_query_ops(tree(tmp_path)) == {"Rows", "Detail"}


def test_match_capture_picks_the_most_specific_route_and_reports_orphans() -> None:
    routes = ["/screeners", "/screeners/new", "/screeners/$id", "/explore"]
    per, orphans = wpo.match_capture(
        routes, ["/screeners/new", "/screeners/vrp", "/explore?sel=AAPL", "/nowhere"]
    )
    assert per["/screeners/new"] == ["/screeners/new"]
    assert per["/screeners/$id"] == ["/screeners/vrp"]
    assert per["/explore"] == ["/explore?sel=AAPL"]
    assert per["/screeners"] == []
    assert orphans == ["/nowhere"]


def test_reference_kinds_conditional_and_arrow_scopes() -> None:
    text = (
        "export function P() {\n  const a = useA();\n  const b = flag && useB();\n"
        "  return <X onClick={() => useC()} y={useD({ enabled: x })} />;\n}\n"
    )
    kinds = dict(wpo.reference_kinds(text))
    assert kinds["useA"] == wpo.LOAD
    assert kinds["useB"] == wpo.MAYBE
    assert kinds["useC"] == wpo.HANDLER
    assert kinds["useD"] == wpo.MAYBE


def test_generated_document_index_is_not_followed_and_hand_written_queries_count(
    tmp_path: Path,
) -> None:
    src = tree(tmp_path)
    (src / "shared/api/generated").mkdir(parents=True)
    # codegen's `graphql()` indexes every document: reaching it must not reach them all
    (src / "shared/api/generated/gql.ts").write_text(
        "const documents = { x: RowsDocument };\n"
        "export function graphql(s) { return documents[s]; }\n"
    )
    page = src / "pages/list/ui/ListPage.tsx"
    page.write_text(
        "import { graphql } from '@/shared/api/generated/gql';\n"
        "import { useRows } from '@/entities/rows';\n"
        "const HandDoc = gql<Q>(`query Hand($id: String!) { hand(id: $id) }`);\n"
        "export function ListPage() { graphql('x'); useRows(); return HandDoc; }\n"
    )
    assert wpo.all_query_ops(src) == {"Rows", "Detail", "Hand"}
    pages, _ = wpo.static_page_ops(src, wpo.enumerate_routes(src))
    assert pages["/items"] == {"Rows": wpo.LOAD, "Hand": wpo.LOAD}


def test_a_loader_built_above_the_route_and_a_dynamic_document_import_are_followed(
    tmp_path: Path,
) -> None:
    """The ops missed on the real tree: `...loading` keeps `page.prefetchXReads` outside the route
    block, and a hook that loads its document with `await import('./doc')`."""
    src = tree(tmp_path)
    routes = src / "app/routes/trader.tsx"
    text = routes.read_text()
    block = text[text.index("  ...pageRoute(ListPage") : text.index("  component: ListPage,")]
    text = text.replace(block, "  ...loading,\n")
    text = text.replace(
        "const listRoute = createRoute({",
        "const loading = pageRoute(ListPage, (page, client) => {\n"
        "  page.prefetchListReads(client);\n});\nconst listRoute = createRoute({",
    )
    routes.write_text(text)
    hooks = src / "entities/rows/api/hooks.ts"
    hooks.write_text(
        hooks.read_text().replace(
            "  return useQuery({ queryFn: () => gql(DetailDoc), enabled: true });",
            "  return useQuery({ queryFn: async () => {\n"
            "    const { LazyDoc } = await import('./lazy-doc');\n"
            "    return gql(LazyDoc);\n  } });",
        )
    )
    (src / "entities/rows/api/lazy-doc.ts").write_text(
        "export const LazyDoc = graphql(`\n  query Lazy { lazy { id } }\n`);\n"
    )
    found = {r.path: r for r in wpo.enumerate_routes(src)}
    assert [n[1] for n in found["/items"].prefetch] == ["prefetchListReads"]
    pages, _ = wpo.static_page_ops(src, list(found.values()))
    assert "Lazy" in pages["/items"]
