"""Every path that serves per-name catalogue values goes through the one data-licence gate
(ADR 0028, ``services.licences``): a module of the read model, the Builder's preview, the
screener run or the API that reads values from the stores must be listed here with the line
that applies the gate, or be listed as exempt with its reason. A new reader fails this test
until it is one or the other, so a value under a personal licence cannot reach a user who
does not hold it by a path nobody listed."""

import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

SRC = REPO_ROOT / "src" / "algotrade" / "services"
# The calls that read stored values of catalogue fields (a rollup, a reference fact, a formula).
RAW = re.compile(
    r"(?<![\w.])(field_view|entity_field_view|fields_view|selection_view|read_expressions"
    r"|rollup_rows|group_view|instrument_view|feature_rows|partition|run_partition|load_series"
    r"|load_feature_values|load_market_feature_values|market_frame|load_chains|load_quotes"
    r"|underlying_quotes)\("
)
SCANNED = (
    SRC / "read",
    SRC / "preview",
    SRC / "screening",
    SRC / "jobs",
    SRC / "live",
    SRC / "explaining",
    REPO_ROOT / "apps" / "api" / "algotrade_api",
)

# module -> the text that applies the gate in it (a read that decides what a viewer sees)
GATED = {
    "services/read/instruments/features.py": "ctx.licences",  # features(names), cells, market
    "services/read/instruments/table.py": "ctx.licences",  # the table's filters and sort
    "services/read/instruments/series.py": "ctx.licences",  # a field's history
    "services/read/instruments/distribution.py": "ctx.licences",  # an aggregate of values
    "services/read/screens/results.py": "run_withheld(",  # stored values, score, reasons, sorts
    "services/read/screens/ideas.py": "run_withheld(",  # a withheld run joins no pool
    "services/read/ops/quality.py": "ctx.licences",  # verification/ibkr: IBKR's values
    "services/read/regime/timeline.py": "ctx.licences",  # a shared cache keyed by the set
    "services/preview/frame.py": "hidden_fields(",  # the Builder's frame (kept per licence set)
    "services/preview/expressions.py": "ctx.licences",  # a formula's sample and dry run
    "services/screening/run.py": "held=held",  # a screener run, so the results it stores
    "services/live/quotes.py": "ctx.licences",  # live IBKR quotes
}
# Callers that must hand the user's licences to a gated function or key.
CALLERS = {
    "services/jobs/handlers.py": "_screen_licences(",  # the screen job: run_screener
    "services/preview/screens.py": "ctx.licences",  # the preview's frame
    "services/read/screens/ideas.py": "run_withheld(",  # the ranking by score
    "services/explaining/regime.py": "ctx.licences",  # the explanation cache key
}
GATED_LOADERS = "reads through a gated loader (load_feature_values / load_series / ctx.licences)"
STORED_OPEN = "stored open data (Cboe chains, chain status, Guide / config, run decisions)"
# Readers that never serve a licensed value to a user, and why.
EXEMPT = {
    "services/selection.py": "the gate itself: fields_view takes ``held`` (its callers pass it)",
    "services/screening/regime.py": "reads the regime label only (open: see the test below)",
    "services/read/context.py": "the partition helper itself; ReadContext.licences lives here",
    "services/read/events/ahead.py": GATED_LOADERS,
    "services/read/events/reference.py": GATED_LOADERS,
    "services/read/market/features.py": GATED_LOADERS,
    "services/read/market/history.py": GATED_LOADERS,
    "services/read/regime/fields.py": GATED_LOADERS,
    "services/read/regime/history.py": GATED_LOADERS,
    "services/read/regime/sources.py": "provenance dates and kinds of a card's series (never a "
    "value), shown to every viewer as the stored-vintage read always was: macro_asof's columns "
    "carry the series' licence, but this read ignores it (owner decision pending, PR)",
    "services/read/events/instrument_events.py": STORED_OPEN,
    "services/read/instruments/chains.py": STORED_OPEN,
    "services/read/ops/ingestion.py": STORED_OPEN,
    "services/read/screens/runs.py": "run rows: names and decisions; values are gated in results",
    "services/read/screens/views.py": "saved views: configs, no values",
    "services/read/evaluation/pick_edges.py": "stored pick ids (names, no value) of an edge, "
    "and a row whose rank is withheld is not judged (ADR 0081)",
    "services/read/evaluation/runs.py": "run results carry their recorded licence (ADR 0064)",
    "services/read/ops/backtests.py": "backtest results of the user's own runs (ADR 0064)",
}


def _modules() -> dict[str, str]:
    found: dict[str, str] = {}
    for root in SCANNED:
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            if RAW.search(text):
                found[_name(path)] = text
    return found


def _name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT)
    return str(rel.relative_to("src/algotrade")) if rel.parts[0] == "src" else str(rel)


def test_every_module_reading_values_applies_the_licence_gate_or_says_why_not() -> None:
    unlisted = sorted(set(_modules()) - set(GATED) - set(EXEMPT))
    assert unlisted == [], (
        "these modules read catalogue values: apply services.licences (ctx.licences / "
        f"hidden_fields) and list them in GATED, or justify them in EXEMPT: {unlisted}"
    )


@pytest.mark.parametrize(("module", "proof"), [*GATED.items(), *CALLERS.items()])
def test_a_gated_module_still_applies_the_gate(module: str, proof: str) -> None:
    assert proof in (SRC.parent / module).read_text(), f"{module} no longer contains {proof!r}"


def test_the_gate_lists_name_modules_that_exist() -> None:
    missing = [m for m in (*GATED, *CALLERS, *EXEMPT) if not (SRC.parent / m).is_file()]
    assert missing == []


def test_the_python_screeners_read_only_open_tables() -> None:
    """A screener that is code, not rules (``impl`` not in ``RULE_IMPLS``), reads its
    ``requires`` tables whole, outside the gate: none of them may be a personal-licence table."""
    from algotrade.services.features import site_features  # noqa: PLC0415
    from algotrade.strategies.screeners.registry import SCREENERS  # noqa: PLC0415

    personal = {g.table for g in site_features().code.values()
                if any(f.licence == "personal" for f in g.features)}  # fmt: skip
    needs = {t for cls in SCREENERS.values() for t in getattr(cls, "requires", ())}
    assert needs & personal == set()


def test_the_regime_label_a_screen_gate_reads_is_open() -> None:
    from algotrade.config.strategy.regime import REGIME_LABEL  # noqa: PLC0415
    from algotrade.services.features import site_features  # noqa: PLC0415
    from algotrade.services.licences import licence_of  # noqa: PLC0415

    assert licence_of(site_features(), REGIME_LABEL) == "open"


def test_callers_that_read_for_no_user_pass_the_named_harness_licences() -> None:
    """``held`` has no default (fail closed): the edge harness, backtests and training pass
    ``HARNESS_ALL`` by name, so each is a line a reviewer can find (ADR 0069)."""
    call = re.compile(r"(?<![\w.])(fields_view|select|screen_session)\(")
    bare = [
        _name(p)
        for root in (SRC / "evaluation", SRC / "backtests")
        for p in sorted(root.rglob("*.py"))
        if call.search(p.read_text()) and "HARNESS_ALL" not in p.read_text()
    ]
    assert bare == []


def test_every_shared_cache_of_gated_values_carries_the_licence_set() -> None:
    api = (REPO_ROOT / "apps/api/algotrade_api/graphql/response_cache.py").read_text()
    assert "viewer.licences" in api  # the response key, SHARED operations included
    assert "licences" in (SRC / "explaining/cache.py").read_text()  # the explanation key
    assert "held" in (SRC / "read/regime/timeline.py").read_text()  # the episode-signals key
