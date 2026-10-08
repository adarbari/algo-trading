"""``docs/edges.md`` (ADR 0053): rendered from the edge documents, candidates first, each with
its outcome, universe, the nine answers and the sources; the committed page is up to date."""

from algotrade.config.edges.document import parse_edge
from algotrade.config.edges.loading import load_edges
from algotrade.config.edges.page import PATH, render
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.config.edges.test_document import document

RULE = {"field": "instrument.status", "op": "eq", "value": "ACTIVE"}


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
            schedule="on_event:earnings_scheduled",
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
            },
            sources=[{"title": "A paper", "url": "https://example.org"}],
        ),
        "gone",
        "gone.toml",
    )
    page = render([closed, open_edge])
    assert page.index("| Drift (`drift`) | candidate") < page.index("| Drift (`gone`) | rejected")
    assert "excess return, over 6 sessions, vs SPY, starting -5 sessions from the event" in page
    assert "costs 20 bps" in page
    assert (
        "hit target, over 1 session, hit when realised_to_implied_vol is below 1, max drawdown 0.5"
        in page
    )
    assert "on each `earnings_scheduled` (a next report date known" in page
    universe = "`instrument.status eq 'ACTIVE'` or (not `instrument.status eq 'ACTIVE'`)"
    assert f"**Universe:** {universe}" in page
    assert "**Universe:** preset `liquid_optionable`" in page
    assert "**Why rejected:** Decayed." in page
    assert "**Notes:** A proxy." in page
    assert "9. **Decoys:** (not answered)" in page
    assert "- A paper <https://example.org>" in page
    assert "**Screeners:** `vrp_scanner`" in page
    assert "**Baselines:** none yet" in page


def test_the_committed_page_is_up_to_date() -> None:
    edges = load_edges(FileConfigStore(REPO_ROOT / "config", local=False))
    committed = (REPO_ROOT / PATH).read_text()
    assert committed == render(edges), f"{PATH} is out of date: run `make features-doc`"
