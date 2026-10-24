# ruff: noqa: E501  (the fake Playwright page is an embedded JavaScript string)
"""`scripts/perf/views.py`, `view_coverage.py`, `capture_views.py` and `view_crawler.mjs`:
view enumeration on a fixture route tree, the coverage diff, the views-file reader, the crawler's
real-store guard and the crawl loop on a fake Playwright page (no browser, no server, no store)."""

import argparse
import importlib.util
import json
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

PERF = Path(__file__).resolve().parents[3] / "scripts" / "perf"
sys.path.insert(0, str(PERF))
import web_page_ops as wpo  # noqa: E402  (found through PERF on sys.path)


def _load(name: str, file: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, PERF / file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vw = _load("views", "views.py")
cov = _load("view_coverage", "view_coverage.py")
cap = _load("capture_views", "capture_views.py")

FILES = {
    "app/routes/root.ts": "export const rootRoute = createRootRoute({});",
    "app/routes/trader.tsx": """
export const traderRoute = createRoute({ getParentRoute: () => rootRoute, id: 'trader' });
const ListPage = lazyPage(() => import('@/pages/list'), 'ListPage');
const ItemPage = lazyPage(() => import('@/pages/item'), 'ItemPage');
export const listRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'items',
  validateSearch: validateItemsSearch,
  ...pageRoute(ListPage),
  component: ListPage,
});
export const itemRoute = createRoute({
  getParentRoute: () => traderRoute,
  path: 'items/$id',
  ...pageRoute(ItemPage),
  component: ItemPage,
});
const VIEWS = ['mine', 'rejected'];
export function validateItemsSearch(search) {
  const { edge, view } = search;
  const found = VIEWS.find((v) => v === view);
  return { ...(typeof edge === 'string' && edge ? { edge } : {}), ...(found ? { view: found } : {}) };
}
""",
    "pages/list/index.ts": "export { ListPage } from './ListPage';",
    "pages/list/ListPage.tsx": """
import { useRows, useChart } from '@/entities/rows';
const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'chart', label: 'Chart' },
  { id: 'nowhere', label: 'Nowhere' },
];
export function ListPage() {
  const rows = useRows();
  const [tab, setTab] = useState('overview');
  return (
    <Tabs items={TABS} value={tab} onChange={setTab} label="View">
      {tab === 'chart' && <ChartTab />}
      <Disclosure label="More detail">{rows}</Disclosure>
    </Tabs>
  );
}
function ChartTab() {
  const c = useChart();
  return c;
}
""",
    "pages/item/index.ts": "export { ItemPage } from './ItemPage';",
    "pages/item/ItemPage.tsx": "export function ItemPage() { return null; }",
    "entities/rows/index.ts": "export { useRows, useChart } from './hooks';",
    "entities/rows/hooks.ts": """
const RowsDoc = graphql(`
  query Rows { rows { id } }
`);
const ChartDoc = graphql(`
  query Chart { chart { id } }
`);
export function useRows() {
  return useQuery({ queryFn: () => gql(RowsDoc) });
}
export function useChart() {
  return useQuery({ queryFn: () => gql(ChartDoc) });
}
""",
}


def tree(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    return tmp_path


# ---- enumeration ----------------------------------------------------------------------------


def test_enumerates_routes_search_values_ids_tabs_and_disclosures(tmp_path: Path) -> None:
    found = vw.enumerate_views(tree(tmp_path))
    with_edge = "/items?edge={edge}"
    assert set(found) == {
        "(shell)",
        "/items",
        "/items?view=mine",
        "/items?view=rejected",
        with_edge,
        f"{with_edge} > tab:View:Overview",
        f"{with_edge} > tab:View:Chart",
        f"{with_edge} > tab:View:Nowhere",
        f"{with_edge} > expand:More detail",
        "/items/:id",
    }


def test_view_ids_are_stable_and_pattern_based() -> None:
    assert vw.pattern_id("/guide/edges/$") == "/guide/edges/:splat"
    assert vw.pattern_id("/edges/$id/edit") == "/edges/:id/edit"
    clicks = [{"kind": "tab", "group": "View", "name": "Chart"}]
    assert vw.view_id("/explore", {"sel": "{instrument}"}, clicks) == (
        "/explore?sel={instrument} > tab:View:Chart"
    )


def test_a_tab_view_lists_its_own_operations_not_the_pages(tmp_path: Path) -> None:
    views = vw.enumerate_views(tree(tmp_path))
    chart = next(v for k, v in views.items() if k.endswith("tab:View:Chart"))
    assert chart["ops"] == ["Chart"]
    assert chart["target"] is True
    overview = next(v for k, v in views.items() if k.endswith("tab:View:Overview"))
    assert overview["ops"] == [] and overview["target"] is False  # no component shows 'overview'
    base = views["/items"]
    assert "Rows" in base["ops"] and "Rows" not in base["uncertain"]
    assert "Chart" in base["uncertain"]  # behind `tab === 'chart' &&`: the page may not send it


def test_search_values_become_views_and_id_params_get_placeholders(tmp_path: Path) -> None:
    views = vw.enumerate_views(tree(tmp_path))
    assert "/items?view=mine" in views and "/items?view=rejected" in views
    assert views["/items?edge={edge}"]["search"] == {"edge": "{edge}"}
    assert views["/items/:id"]["params"] == {"id": "link"}
    # the tabs hang off the id-carrying variant: they exist only with an edge chosen
    tabs = [k for k in views if " > tab:" in k]
    assert tabs and all(k.startswith("/items?edge={edge} > ") for k in tabs)


# ---- the views file -------------------------------------------------------------------------


def test_merge_static_keeps_captures_and_discovered_views() -> None:
    existing = {
        "views": {
            "/a": {"captured": {"status": "ok", "requests": []}, "source": "static"},
            "/a > tab:X": {"source": "discovered", "captured": {"status": "ok"}},
            "/gone": {"source": "static"},
        }
    }
    merged = vw.merge_static(existing, {"/a": {"ops": ["A"], "source": "static"}})
    assert merged["/a"]["captured"]["status"] == "ok" and merged["/a"]["ops"] == ["A"]
    assert "/a > tab:X" in merged and "/gone" not in merged


def test_view_operations_prefer_the_capture_then_the_static_ops() -> None:
    doc = {
        "views": {
            "/v": {
                "ops": ["Rows"],
                "captured": {
                    "requests": [
                        {
                            "op": "Rows",
                            "query": "query Rows {x}",
                            "variables": {"id": 1},
                            "count": 2,
                        },
                        {"op": "Rows", "query": "query Rows {x}", "variables": {"id": 2}},
                    ]
                },
            },
            "/static": {"ops": ["Known"]},
            "/empty": {"ops": []},
        }
    }
    known = {"Known": {"query": "q", "variables": {}}}
    ops, by_view = vw.view_operations(doc, ["/v", "/static"], known)
    assert ops["Rows [/v]"]["variables"] == {"id": 1} and by_view["/v"] == ["Rows [/v]"]
    assert by_view["/static"] == ["Known [/static]"]
    # a second view of the same operation keeps its own variables
    two = {
        "views": {
            "/a": doc["views"]["/v"],
            "/b": {
                "captured": {"requests": [{"op": "Rows", "query": "q", "variables": {"id": 9}}]}
            },
        }
    }
    again, _ = vw.view_operations(two, ["/a", "/b"], known)
    assert again["Rows [/a]"]["variables"] == {"id": 1} and again["Rows [/b]"]["variables"] == {
        "id": 9
    }
    with pytest.raises(vw.SelectionError, match="not in the views file"):
        vw.view_operations(doc, ["/nope"], known)
    with pytest.raises(vw.SelectionError, match="no operation"):
        vw.view_operations(doc, ["/empty"], known)
    with pytest.raises(vw.SelectionError, match="no captured document"):
        vw.view_operations({"views": {"/s": {"ops": ["Lost"]}}}, ["/s"], known)


def test_latency_view_flag_is_parsed_and_profile_takes_one() -> None:
    lat = _load("perf_api_latency_views", "api_latency.py")
    args = lat.parse_args(["--view", "/a", "--view", "/b", "--profile"])
    assert args.view == ["/a", "/b"] and lat.run_needs_url(args)
    assert "one --page or --view" in (lat.profile_selection_error(args) or "")
    one = lat.parse_args(["--view", "/a", "--profile"])
    assert lat.profile_selection_error(one) is None


# ---- coverage -------------------------------------------------------------------------------


def test_coverage_lists_untriggered_operations_with_where_they_should_be() -> None:
    doc = {
        "views": {
            "/a": {
                "clicks": [],
                "ops": ["A"],
                "interaction": ["Drawer"],
                "captured": {"status": "ok", "requests": [{"op": "A", "count": 3}]},
            },
            "/a > tab:T": {
                "clicks": [{"kind": "tab", "name": "T"}],
                "ops": ["B"],
                "captured": {
                    "status": "ok",
                    "requests": [
                        {"op": "A", "count": 1, "trigger": "load"},
                        {"op": "B", "count": 1, "trigger": "click:tab:T"},
                    ],
                },
            },
            "/empty": {"clicks": [], "ops": [], "captured": {"status": "ok", "requests": []}},
            "/todo": {"clicks": [], "ops": ["C"]},
        }
    }
    old = {"/a": [{"kind": "graphql", "op": "A"}, {"kind": "rest"}]}
    rep = cov.coverage(doc, {"A", "B", "C", "Drawer", "Dead"}, old)
    assert rep["triggered"]["A"] == {"/a": 3}  # a sub-view's load requests are its parent's
    assert rep["triggered"]["B"] == {"/a > tab:T": 1}
    assert rep["untriggered"] == {"C": ["/todo"], "Drawer": ["/a"], "Dead": []}
    assert rep["no_data"] == ["/empty"] and rep["uncaptured"] == ["/todo"]
    assert rep["delta"]["added_ops"] == ["B"] and rep["delta"]["old_routes"] == 1
    text = cov.render(doc, rep, "now")
    assert "| Dead | nowhere" in text and "`/todo`" in text


# ---- the crawler's real-store guard -----------------------------------------------------------


@pytest.fixture(autouse=True)
def _web_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "web" / "node_modules").mkdir(parents=True)
    monkeypatch.setattr(cap, "WEB", tmp_path / "web")


def _args(tmp_path: Path, **over: object) -> argparse.Namespace:
    views = tmp_path / "views.json"
    views.write_text('{"views": {}}')
    base = {
        "data_url": f"file://{tmp_path / 'clone'}",
        "max_views": 20,
        "only_route": None,
        "view_timeout": 60,
        "depth": 2,
        "max_controls": 40,
        "retry": False,
        "views_file": str(views),
    }
    return argparse.Namespace(**{**base, **over})


def test_crawler_refuses_without_a_clone_or_on_the_real_store(tmp_path: Path) -> None:
    real = tmp_path / "var" / "data"
    real.mkdir(parents=True)
    with pytest.raises(cap.al.RefusalError, match="needs --data-url"):
        cap.check_crawl(_args(tmp_path, data_url=None), [real])
    with pytest.raises(cap.al.RefusalError, match="real local store"):
        cap.check_crawl(_args(tmp_path, data_url=f"file://{real}"), [real])
    with pytest.raises(cap.al.RefusalError, match="real local store"):
        cap.check_crawl(_args(tmp_path, data_url=f"file://{real / 'x'}"), [real])
    assert cap.check_crawl(_args(tmp_path), [real]).endswith("clone")


def test_crawler_refuses_unbounded_runs_and_a_missing_views_file(tmp_path: Path) -> None:
    for over in ({"max_views": 0}, {"max_views": 10_000}):
        with pytest.raises(cap.al.RefusalError, match="--max-views"):
            cap.check_crawl(_args(tmp_path, **over), [])
    with pytest.raises(cap.al.RefusalError, match="does not exist"):
        cap.check_crawl(_args(tmp_path, views_file=str(tmp_path / "none.json")), [])


def test_only_loopback_and_never_the_live_port() -> None:
    assert cap.check_local("http://127.0.0.1:11368") == "http://127.0.0.1:11368"
    for bad in ("http://127.0.0.1:8000", "https://prod.example.com:11368", "http://127.0.0.1"):
        with pytest.raises(cap.al.RefusalError):
            cap.check_local(bad)


class _FakeApi:
    def __init__(self, mode: str, data_url: str | None = None) -> None:
        self.mode, self.data_url, self.url, self.closed = (
            mode,
            data_url,
            "http://127.0.0.1:11368",
            False,
        )

    def close(self) -> None:
        self.closed = True


def test_vite_is_started_with_our_api_as_its_proxy_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """The leak the architect found: Vite's default proxy target is the live API on :8000."""
    monkeypatch.setattr(cap.al, "free_port", lambda: 11369)
    seen: dict = {}

    def popen(cmd, **kw):  # type: ignore[no-untyped-def]
        seen.update(cmd=cmd, env=kw["env"])
        return object()

    api, _, web = cap.start_servers("file:///clone", api_factory=_FakeApi, popen=popen)
    assert api.mode == "uncached" and api.data_url == "file:///clone"
    assert seen["env"]["API_PROXY_TARGET"] == api.url == "http://127.0.0.1:11368"
    assert web == "http://127.0.0.1:11369" and seen["cmd"][-2:] == ["--port", "11369"]


def test_servers_on_the_live_port_are_refused_and_the_api_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cap.al, "free_port", lambda: 8000)
    made: list = []

    def factory(mode: str, data_url: str | None = None) -> _FakeApi:
        made.append(_FakeApi(mode, data_url))
        return made[-1]

    with pytest.raises(cap.al.RefusalError):
        cap.start_servers("file:///clone", api_factory=factory, popen=lambda *a, **k: object())
    assert made[0].closed is True
    with pytest.raises(cap.al.RefusalError):
        cap.vite_env("http://127.0.0.1:8000", {})


def test_vite_group_is_killed_not_just_npx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cap.al, "free_port", lambda: 11369)
    kw: dict = {}
    cap.start_servers("file:///c", api_factory=_FakeApi, popen=lambda c, **k: kw.update(k))
    assert kw["start_new_session"] is True

    class Proc:
        pid = 4242

        def __init__(self, stubborn: bool) -> None:
            self.stubborn = stubborn

        def wait(self, timeout: float) -> None:
            if self.stubborn and not sent[-1] == cap.signal.SIGKILL:
                raise cap.subprocess.TimeoutExpired("x", timeout)

    sent: list = [None]

    def alive_after(pid: int, sig: int) -> None:
        sent.append(sig)
        if sig == 0 and sent.count(0) > 1:
            raise ProcessLookupError

    # the leader exits on SIGTERM; the probe finds a surviving child, which gets the SIGKILL
    cap.stop_group(Proc(False), alive_after)
    assert sent[1:] == [cap.signal.SIGTERM, 0, cap.signal.SIGKILL]
    sent[:] = [None]

    def clean(pid: int, sig: int) -> None:
        sent.append(sig)
        if sig == 0:
            raise ProcessLookupError  # nothing of the group is left

    cap.stop_group(Proc(False), clean)
    assert sent[1:] == [cap.signal.SIGTERM, 0]
    sent[:] = [None]

    def kill(pid: int, sig: int) -> None:
        sent.append(sig)
        if sig == 0:
            raise ProcessLookupError

    cap.stop_group(Proc(True), kill)
    assert sent[1:] == [cap.signal.SIGTERM, cap.signal.SIGKILL, 0]

    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError

    cap.stop_group(Proc(False), gone)  # already dead: no error

    class Denied(Proc):
        terminated = False

        def terminate(self) -> None:
            self.terminated = True

    def no_permission(pid: int, sig: int) -> None:
        raise PermissionError

    d = Denied(False)
    cap.stop_group(d, no_permission)  # the group cannot be signalled, nor probed: no error
    assert d.terminated is True


def test_signal_handlers_are_installed_before_the_servers_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list = []
    monkeypatch.setattr(cap.signal, "signal", lambda sig, h: events.append(("signal", sig)))
    monkeypatch.setattr(cap, "check_crawl", lambda *a, **k: "file:///c")
    monkeypatch.setattr(cap.al, "real_stores", lambda *a: [])
    monkeypatch.setattr(cap.al, "main_checkout_of", lambda *a: None)

    def start(_: str) -> None:
        events.append("start")
        raise RuntimeError("stop here")

    monkeypatch.setattr(cap, "start_servers", start)
    with pytest.raises(RuntimeError):
        cap.main(["--data-url", "file:///c", "--views-file", str(tmp_path / "v.json")])
    assert events == [("signal", cap.signal.SIGTERM), ("signal", cap.signal.SIGHUP), "start"]


@pytest.fixture(autouse=True)
def _restore_stop_signals():  # type: ignore[no-untyped-def]
    """stop_all ignores SIGTERM / SIGHUP for real in some tests: put the handlers back."""
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGHUP)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def test_cleanup_ignores_a_second_sigterm_and_sighup(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []
    monkeypatch.setattr(cap.signal, "signal", lambda sig, h: events.append((sig, h)))

    class Api:
        def close(self) -> None:
            events.append("api closed")

    cap.stop_all(Api(), object(), lambda vite: events.append("vite stopped"))
    assert events == [
        (cap.signal.SIGTERM, cap.signal.SIG_IGN),
        (cap.signal.SIGHUP, cap.signal.SIG_IGN),
        "api closed",
        "vite stopped",
    ]


def test_an_interrupt_during_api_startup_stops_the_api_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ctrl-C / SIGTERM inside Api.__init__ (up to 90 s): there is no object yet to close."""
    stopped: list = []

    class Proc:
        returncode = None

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            stopped.append("terminate")

        def wait(self, timeout: float) -> None:
            stopped.append("wait")

    class Client:
        def __init__(self, **kw: object) -> None:
            pass

        def get(self, url: str) -> None:
            raise KeyboardInterrupt  # the interrupt lands in the start-up wait

        def close(self) -> None:
            stopped.append("client closed")

    monkeypatch.setattr(cap.al, "free_port", lambda: 11368)
    monkeypatch.setattr(cap.al.subprocess, "Popen", lambda *a, **k: Proc())
    monkeypatch.setattr(cap.al.httpx, "Client", Client)
    with pytest.raises(KeyboardInterrupt):
        cap.al.Api("uncached", data_url="file:///c")
    assert stopped == ["client closed", "terminate", "wait"]


def test_crawler_refuses_early_without_web_node_modules(tmp_path: Path) -> None:
    (tmp_path / "web" / "node_modules").rmdir()
    with pytest.raises(cap.al.RefusalError, match="node_modules is missing"):
        cap.check_crawl(_args(tmp_path), [])


def test_a_failing_vite_stop_never_leaves_the_api_running() -> None:
    """The orphan API (507 MB, 9 minutes): killpg raised PermissionError in the cleanup path."""

    class Api:
        closed = False

        def close(self) -> None:
            self.closed = True

    class Vite:
        pid, calls = 7, []

        def terminate(self) -> None:
            self.calls.append("terminate")

        def wait(self, timeout: float) -> None:
            return None

    def denied(pid: int, sig: int) -> None:
        raise PermissionError

    vite = Vite()
    cap.stop_group(vite, denied)  # falls back to terminating the process itself
    assert vite.calls == ["terminate"]

    api = Api()

    def boom(_: object) -> None:
        raise RuntimeError("stop failed")

    with pytest.raises(RuntimeError):
        cap.stop_all(api, Vite(), boom)
    assert api.closed is True

    class BadApi(Api):
        def close(self) -> None:
            raise OSError("api stop failed")

    stopped: list = []
    with pytest.raises(OSError):
        cap.stop_all(BadApi(), Vite(), stopped.append)
    assert len(stopped) == 1  # Vite was still stopped


def test_duplicates_note_lists_operations_sent_more_than_once() -> None:
    view = {
        "captured": {
            "status": "ok",
            "requests": [
                {"op": "SessionDate", "count": 2, "trigger": "load"},
                {"op": "EventCalendar", "count": 1, "trigger": "load"},
                {"op": "EventCalendar", "count": 1, "trigger": "scroll"},
                {"op": "Once", "count": 1},
            ],
        }
    }
    assert vw.duplicates(view) == {"EventCalendar": 2, "SessionDate": 2}
    views = {"/c": view, "/todo": {}}
    vw.annotate_duplicates(views)
    assert views["/c"]["captured"]["duplicates"] == {"EventCalendar": 2, "SessionDate": 2}
    assert "captured" not in views["/todo"]
    text = cov.render({"views": views}, cov.coverage({"views": views}, {"Once"}), "now")
    assert "EventCalendar x2" in text and "## Operations a view sends more than once" in text


def test_node_command_carries_the_bounds(tmp_path: Path) -> None:
    cmd = cap.node_command(_args(tmp_path, only_route="/edges", retry=True), "http://a", "http://w")
    assert cmd[-2:] == ["--only-route", "/edges"] and "--max-views" in cmd
    assert cmd[cmd.index("--retry") + 1] == "true" and cmd[cmd.index("--max-controls") + 1] == "40"


# ---- the crawl loop, on a fake Playwright page ------------------------------------------------

FAKE = """
import { crawl, resolveUrl, decide, denied, installGuard, routeMatches, pending } from %(crawler)s;

class FakePage {
  constructor(site) { this.site = site; this.handlers = {}; this.url = ''; this.clicked = []; this.closed = false; }
  on(ev, fn) { this.handlers[ev] = fn; }
  async fire(op, variables = {}) {
    const req = { url: () => 'http://x/api/graphql', method: () => 'POST',
      postDataJSON: () => ({ operationName: op, query: 'query ' + op + ' { x }', variables }) };
    this.handlers.request(req);
    await this.handlers.response({ request: () => req, body: async () => Buffer.from('12345') });
  }
  async goto(url) { this.url = url; this.clicked = []; for (const op of this.site.load(url)) await this.fire(op); }
  async waitForLoadState() {}
  async waitForTimeout() {}
  async evaluate(fn, arg) {
    if (arg?.mode === 'discover') return this.site.controls(this.url, this.clicked);
    if (arg?.mode === 'click') {
      if (!this.site.has(arg.kind, arg.name)) return false;
      this.clicked.push(arg.name);
      for (const op of this.site.click(arg.name)) await this.fire(op);
      return true;
    }
    return undefined;
  }
  async close() { this.closed = true; }
}

const site = {
  load: (url) => (url.startsWith('/edges') ? ['Edges', 'Edges'] : ['Home']),
  controls: (url, clicked) => (clicked.length ? [] : [{ kind: 'tab', name: 'Trades', nth: 0 }, { kind: 'expand', name: 'More', nth: 0 }, { kind: 'expand', name: 'Save as draft', nth: 0 }].filter((c) => !denied(c.name))),
  has: (role, name) => name !== 'Gone',
  click: (name) => (name === 'Trades' ? ['EdgeTrades'] : []),
};
const blocked = [];
const opts = { webUrl: '', maxViews: %(max)d, onlyRoute: undefined, viewTimeoutMs: 1000, depth: 1, maxControls: 10, retry: false, blocked };
const routed = [];
await installGuard({ route: async (_pattern, handler) => {
  const mk = (method, url) => ({ request: () => ({ method: () => method, url: () => url, postData: () => null }), continue: () => routed.push('continue'), abort: (why) => routed.push(why) });
  await handler(mk('GET', 'http://w/api/health'));
  await handler(mk('POST', 'http://w/api/regime/explain'));
  await handler(mk('GET', 'https://fonts.example/x'));
} }, 'http://w', blocked);
const doc = { views: {
  '/edges': { route: '/edges', search: {}, clicks: [], params: {} },
  '/home': { route: '/home', search: {}, clicks: [], params: {} },
  '/edges/:id': { route: '/edges/:id', search: {}, clicks: [], params: { id: 'edge' } },
  '/edges > tab:View:Gone': { route: '/edges', search: {}, clicks: [{ kind: 'tab', group: 'View', name: 'Gone' }], params: {} },
} };
const pages = [];
const saves = [];
const result = await crawl(doc, { instrument: 'AAPL' }, opts, async () => { const p = new FakePage(site); pages.push(p); return p; }, (d) => saves.push(JSON.stringify(d)));
console.log(JSON.stringify({ routed, blocked, result, doc, closed: pages.every((p) => p.closed), saves: saves.length,
  guard: [
    decide('GET', 'http://w/api/health', null, 'http://w').allow,
    decide('POST', 'http://w/api/graphql', JSON.stringify({ query: 'query A { a }' }), 'http://w').allow,
    decide('POST', 'http://w/api/graphql', JSON.stringify([{ query: 'query A { a }' }, { query: 'mutation M { m }' }]), 'http://w').allow,
    decide('POST', 'http://w/api/regime/explain', '{}', 'http://w').allow,
    decide('DELETE', 'http://w/api/x', null, 'http://w').allow,
    decide('GET', 'http://127.0.0.1:8000/health', null, 'http://w').allow,
    decide('POST', 'http://w/api/graphql', 'not json', 'http://w').allow,
  ],
  routes: [routeMatches('/edges/:id', '/edges'), routeMatches('/edgesx', '/edges'), routeMatches('/guide/a', '/guide/*'), routeMatches('/x', undefined), routeMatches('/edges', '/guide/*')],
  denied: ['Save as draft', 'Delete', 'Follow edge', 'Regime', 'Where it worked'].map(denied),
  pendingOnly: pending({ views: { a: { route: '/a' }, b: { route: '/b', captured: {} }, c: { route: '/a/x' } } }, { onlyRoute: '/a' }),
  url: resolveUrl({ route: '/e/:id', search: { s: '{instrument}' }, params: { id: 'edge' } }, { edge: 'm 1', instrument: 'AAPL' }),
  nourl: resolveUrl({ route: '/e', search: { s: '{edge}' }, params: {} }, {}) }));
"""


def _run_fake(max_views: int) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = FAKE % {"crawler": json.dumps((PERF / "view_crawler.mjs").as_uri()), "max": max_views}
    done = subprocess.run(
        [node, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_crawl_records_requests_per_view_and_discovers_controls() -> None:
    out = _run_fake(20)
    views = out["doc"]["views"]
    edges = views["/edges"]["captured"]
    assert edges["status"] == "ok"
    row = next(r for r in edges["requests"] if r["op"] == "Edges")
    assert row["count"] == 2 and row["bytes"] == 5 and row["trigger"] == "load"
    # the discovered tab became a view of its own, with the request its click sent
    tab = views["/edges > tab:Trades"]
    assert tab["source"] == "discovered" and tab["clicks"][0]["name"] == "Trades"
    assert {r["op"]: r["trigger"] for r in tab["captured"]["requests"]}["EdgeTrades"] == (
        "click:tab:Trades"
    )
    assert views["/edges > tab:View:Gone"]["captured"]["status"] == "missing"
    # the save-like control is never offered as a view
    assert not [k for k in views if "Save" in k]
    # context guard: reads continue, the REST write and the off-origin call are aborted and named
    assert out["routed"] == ["continue", "blockedbyclient", "blockedbyclient"]
    assert out["blocked"] == ["POST /api/regime/explain", "off-origin https://fonts.example"]
    assert out["guard"] == [True, True, False, False, False, False, False]
    assert out["routes"] == [True, False, True, True, False]
    assert out["denied"] == [True, True, True, False, False]
    assert out["pendingOnly"] == ["a", "c"]
    assert views["/edges/:id"]["captured"]["status"] == "skipped"  # no edge id was picked
    assert out["closed"] is True and out["saves"] >= 4
    assert out["url"] == "/e/m%201?s=AAPL" and out["nourl"] is None


def test_crawl_is_bounded_and_resumable() -> None:
    out = _run_fake(2)
    assert out["result"]["visited"] == 2 and out["result"]["remaining"] >= 1
    captured = [k for k, v in out["doc"]["views"].items() if "captured" in v]
    assert len(captured) == 2


# ---- the gate keeps up with the web (owner decision 2026-10-23) -----------------------------

WEB_SRC = PERF.parents[1] / "apps" / "web" / "src"


@pytest.fixture(scope="module")
def gate_op_set() -> tuple[dict, dict]:
    """What the nightly gate would time from the committed capture (static: no store, no server)."""
    fb = _load("fast_bench", "fast_bench.py")
    distinct, view_ops, skipped = fb.op_set(vw.load_views(fb.CAPTURED_FILE))
    assert not skipped, (
        f"the committed capture has views or operations it cannot measure: {skipped}"
    )
    return distinct, view_ops


def test_every_web_view_and_operation_is_measured_or_listed(gate_op_set: tuple[dict, dict]) -> None:
    """Fitness: each route / tab / panel with a read and each GraphQL operation the web sends is
    measured by the 1 s page gate, or is in architecture/perf_view_coverage.toml (shrink-only).

    Fix: `make api-latency-views`, commit the benchmarks files; the message says what else."""
    distinct, view_ops = gate_op_set
    found = cov.gaps(vw.enumerate_views(WEB_SRC), wpo.all_query_ops(WEB_SRC), distinct, view_ops)
    assert not (msgs := cov.problems(found, cov.load_gaps())), "\n".join(msgs)


GAPS = {"view": {"/old": "not yet captured"}, "operation": {"Old": "not yet captured"}}


def test_a_new_view_or_operation_fails_with_the_one_line_fix() -> None:
    found = {"views": ["/new?edge={edge}"], "stale": ["/gone"], "operations": ["NewOp", "Old"]}
    msgs = cov.problems(found, GAPS)
    text = "\n".join(msgs)
    assert "view `/new?edge={edge}` is not measured by the 1 s page gate" in text
    assert "operation `NewOp` is not measured" in text
    assert "make api-latency-views" in text and "VARIABLE_RESOLVERS" in text
    assert "view `/gone` that the web no longer has" in text
    assert "`Old`" not in text  # listed, still a gap: fine
    assert "view `/old`" in text and "delete the entry" in text  # listed, no longer a gap


def test_an_exception_entry_needs_a_reason_and_covered_ones_must_go() -> None:
    found = {"views": ["/old"], "stale": [], "operations": ["Old"]}
    assert cov.problems(found, GAPS) == []
    assert any("no reason" in m for m in cov.problems(found, {**GAPS, "operation": {"Old": " "}}))


def test_the_committed_exception_list_parses_and_has_a_reason_each() -> None:
    gaps = cov.load_gaps()
    assert all(r.strip() for kind in gaps.values() for r in kind.values())


def test_sync_adds_measurable_new_views_keeps_captures_and_skips_listed_ones() -> None:
    old = {
        "views": {
            "/a": {"source": "static", "ops": ["A"], "captured": {"requests": []}},
            "/found": {"source": "discovered", "ops": ["Z"]},
        }
    }
    web = {
        "/a": {"source": "static", "ops": ["A", "A2"]},
        "/new": {"source": "static", "ops": ["N"]},
        "/listed": {"source": "static", "ops": ["L"]},
        "/noops": {"source": "static", "ops": []},
    }
    out = cov.sync_captured(old, web, {"/listed"})
    assert set(out) == {"/a", "/new", "/found"}
    assert out["/a"]["ops"] == ["A", "A2"] and "captured" in out["/a"]


def test_the_nightly_drift_flag_counts_uncovered_operations_and_those_not_listed(
    tmp_path: Path,
) -> None:
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "q.ts").write_text(
        "const a = graphql(`query Seen { a }`);\nconst b = graphql(`query Fresh { b }`);\n"
        "const c = graphql(`query Old { c }`);\n"
    )
    drift = cov.web_ops_not_measured({"s": {"name": "Seen"}}, tmp_path)
    assert drift["all"] == ["Fresh", "Old"]
    assert drift["new"] == ["Fresh", "Old"]  # neither is in the committed exception list
    assert cov.drift_line(drift).startswith("COVERAGE 2 operations not covered by the gate (")
    assert (
        cov.web_ops_not_measured({n: {"name": n} for n in ("Seen", "Fresh", "Old")}, tmp_path) == {}
    )


def test_the_exception_lists_only_shrink(tmp_path: Path) -> None:
    assert cov.pin_problems() == []  # the committed pins equal the committed lists
    f = tmp_path / "x.toml"
    f.write_text(
        '[baseline]\nmax_operation = 1\nmax_view = 0\n[[operation]]\nname="A"\n[[operation]]\nname="B"\n'
    )
    assert "grew to 2" in cov.pin_problems(f)[0]
    f.write_text("[baseline]\nmax_operation = 1\nmax_view = 0\n")
    assert "shrank to 0" in cov.pin_problems(f)[0]


def test_a_broken_exception_file_or_web_walk_cannot_crash_or_change_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fb = _load("fast_bench", "fast_bench.py")
    bad = tmp_path / "bad.toml"
    bad.write_text("not [valid toml")
    monkeypatch.setattr(cov, "GAPS_FILE", bad)
    assert fb.report_sets({"a#1": {"name": "Viewer"}}, {"/": ["a#1"]}, {}, False) == {}
    assert "COVERAGE unavailable" in capsys.readouterr().out
    monkeypatch.setattr(cov.wpo, "all_query_ops", lambda *_: 1 / 0)
    assert fb.report_sets({}, {}, {}, False) == {}


def test_every_measured_operation_has_a_resolvable_variable_set(
    gate_op_set: tuple[dict, dict],
) -> None:
    """Fitness (hand run 9b, 2026-10-24: a new operation entered the measured set and failed the
    nightly's integrity check): each timed operation either carries every required variable or
    has a `VARIABLE_RESOLVERS` entry that fills it from the clone; an `empty_ok` name is a real
    web operation. A legitimately empty answer needs `empty_ok` in benchmarks/perf_bar.toml
    (owner approval, docs/decisions/log.md); missing variables need a resolver in fast_bench.py."""
    fb = _load("fast_bench", "fast_bench.py")
    distinct, _ = gate_op_set
    gaps = []
    for d in distinct.values():
        required = fb.pdocs.required_variables(d["query"])
        resolved = set(fb.VARIABLE_RESOLVERS.get(d["name"], {}))
        if missing := sorted(v for v in required if v not in d["variables"] and v not in resolved):
            gaps.append(f"{d['name']}: no value or resolver for {missing}")
    assert not gaps, "\n".join(gaps)
    empty_ok = set(fb.load_bar().get("empty_ok", []))
    assert empty_ok <= wpo.all_query_ops(WEB_SRC), "empty_ok names an operation the web lacks"
