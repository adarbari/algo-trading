"""``docs/edges.md`` (ADR 0053): rendered from the edge documents, candidates first, each with
its outcome, universe, the nine answers and the sources; the committed page is up to date."""

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.page import DIR, PATH, pages
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import document

RULE = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}


def render(edges: list) -> str:
    """Every page joined: the assertions look at the content, the split tests at the layout."""
    return "\n".join(pages(edges).values())


def test_the_page_lists_edges_by_status_with_their_answers() -> None:
    open_edge = parse_edge(
        document(
            outcome={
                "kind": "excess_return",
                "horizon_sessions": [6],
                "benchmark": "SPY",
                "start_offset_sessions": -5,
                "cost_bps": 20,
            },
            schedule="on_event:earnings_expected",
            universe={"where": {"any": [RULE, {"not": RULE}]}},
            screeners=["vrp_scanner"],
            notes="A proxy.",
        ),
        "drift",
        "drift.toml",
    )
    closed = parse_edge(
        document(
            id="gone",
            status="rejected",
            rejection_reason="Decayed.",
            quality_bar={},
            universe="liquid_optionable",
            schedule="every_session",
            outcome={
                "kind": "hit_target",
                "horizon_sessions": [1],
                "benchmark": "none",
                "target": 1,
                "measure": "realised_to_implied_vol",
                "direction": "below",
                "max_drawdown": 0.5,
                "start_offset_sessions": 1,
            },
            sources=[{"title": "A paper", "url": "https://example.org"}],
        ),
        "gone",
        "gone.toml",
    )
    page = render([closed, open_edge])
    assert page.index("| Drift (`drift`) | candidate") < page.index("| Drift (`gone`) | rejected")
    assert pages([closed, open_edge]).keys() == {PATH, f"{DIR}/other.md"}
    assert "excess return, over 6 sessions, vs SPY, starting -5 sessions from the event" in page
    assert "costs 20 bps" in page
    assert (
        "hit target, over 1 session, entered 1 session after the decision session, "
        "hit when realised_to_implied_vol is below 1, max drawdown 0.5" in page
    )
    assert "on each `earnings_expected` (a next report expected" in page
    universe = "`instrument.status eq 'ACTIVE'` or (not `instrument.status eq 'ACTIVE'`)"
    assert f"**Universe:** {universe}" in page
    assert "**Universe:** preset `liquid_optionable`" in page
    assert "**Why rejected:** Decayed." in page
    assert "**Notes:** A proxy." in page
    assert "9. **Decoys:** (not answered)" in page
    assert "- A paper <https://example.org>" in page
    assert "**Screeners:** `vrp_scanner`" in page
    assert "**Baselines:** none yet" in page
    assert "**Published:**" not in page


def test_a_published_figure_is_shown_with_its_source() -> None:
    e = parse_edge(
        document(
            sources=[{"title": "A paper"}],
            published={
                "measure": "decile_spread",
                "value": 0.0131,
                "horizon_sessions": 20,
                "source": 0,
                "sample": 25,
            },
        ),
        "drift",
        "drift.toml",
    )
    assert "- **Published:** decile spread 1.31% over 20 sessions (A paper, 25 years)" in render(
        [e]
    )


def test_edges_are_split_by_family_and_the_index_links_each() -> None:
    a = parse_edge(document(id="aa", family="A"), "aa", "aa.toml")
    b = parse_edge(document(id="bb", family="B"), "bb", "bb.toml")
    none = parse_edge(document(id="cc"), "cc", "cc.toml")
    out = pages([none, b, a])
    assert out.keys() == {PATH, f"{DIR}/a.md", f"{DIR}/b.md", f"{DIR}/other.md"}
    assert "[family B](edges/b.md)" in out[PATH]
    assert "[no family](edges/other.md)" in out[PATH]
    assert "## Drift (`bb`)" in out[f"{DIR}/b.md"] and "`aa`" not in out[f"{DIR}/b.md"]
    assert "## Drift" not in out[PATH]


def test_the_committed_pages_are_up_to_date() -> None:
    edges = load_edges(FileConfigStore(REPO_ROOT / "config", local=False))
    expected = pages(edges)
    for rel, text in expected.items():
        assert (REPO_ROOT / rel).read_text() == text, f"{rel} is out of date: make features-doc"
    on_disk = {str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / DIR).glob("*.md")}
    assert on_disk == expected.keys() - {PATH}, "a stale family page: run `make features-doc`"
