"""The price-source slices of an edge evaluation (ADR 0088 decision 11): an edge reading option
trade rows splits at the Cboe cutover into an open slice and a history slice; any other edge is one
unsplit slice; ``check_open`` refuses an open slice that joined licensed rows."""

from dataclasses import replace
from datetime import date

import pytest

from algotrade.config.edges.document import job_name
from algotrade.config.edges.positions.chain import OPTION_HISTORY, reads_chain
from algotrade.config.edges.positions.templates import load_templates
from algotrade.core.model.errors import AlgoTradeError
from algotrade.core.time.calendar import previous_session
from algotrade.data.chains import FIRST_CBOE_CHAIN_SESSION as CUT
from algotrade.services.evaluation.cross_section.detail.licences import TrialLicences
from algotrade.services.evaluation.cross_section.measures import (
    Slice,
    slice_measures,
)
from algotrade.services.evaluation.cross_section.run.evaluation import VariantResult
from algotrade.services.evaluation.cross_section.run.sources import (
    ALL,
    CBOE,
    SourceSlice,
    check_open,
    source_slices,
)
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.services.evaluation.cross_section.test_measures import A, B

TEMPLATES = load_templates(FileConfigStore(REPO_ROOT / "config", local=False))
BEFORE, AFTER = date(2025, 1, 6), date(2026, 11, 2)


def option_edge():
    from tests.unit.services.evaluation.time_series.test_sleeve import sleeve_edge  # noqa: PLC0415

    return sleeve_edge()


def test_an_edge_reading_no_option_rows_is_one_unsplit_slice() -> None:
    from tests.unit.config.edges.test_document import parse  # noqa: PLC0415

    edge = parse()
    assert not reads_chain(edge, TEMPLATES)
    assert source_slices(edge, TEMPLATES, BEFORE, AFTER) == (SourceSlice(ALL, BEFORE, AFTER),)


def test_an_option_edge_splits_at_the_cutover_open_first() -> None:
    open_, history = source_slices(option_edge(), TEMPLATES, BEFORE, AFTER)
    assert open_ == SourceSlice(CBOE, CUT, AFTER)
    assert history == SourceSlice(OPTION_HISTORY, BEFORE, previous_session(CUT))
    assert (open_.job_suffix, history.job_suffix) == ("", OPTION_HISTORY)


def test_empty_slices_are_dropped() -> None:
    edge = option_edge()
    only_history = source_slices(edge, TEMPLATES, BEFORE, date(2026, 9, 1))
    assert [s.source for s in only_history] == [OPTION_HISTORY]
    only_open = source_slices(edge, TEMPLATES, CUT, AFTER)
    assert [s.source for s in only_open] == [CBOE]


def test_a_share_setup_with_an_option_baseline_splits_too() -> None:
    from tests.unit.config.edges.test_document import parse  # noqa: PLC0415

    edge = parse(baselines=["position:short_put"])
    assert reads_chain(edge, TEMPLATES)
    found = source_slices(edge, TEMPLATES, BEFORE, AFTER)
    assert [s.source for s in found] == [CBOE, OPTION_HISTORY]
    shares = parse(baselines=["position:long_shares"])
    assert not reads_chain(shares, TEMPLATES)


def test_the_history_run_is_its_own_trial_log_job() -> None:
    assert job_name("e", "site") == "edge-eval:e:site"
    assert job_name("e", "site", OPTION_HISTORY) == "edge-eval:e:site:option_history"


def _result(outcome: str) -> VariantResult:
    lic = TrialLicences("open", "open", "open", "open", outcome=outcome)
    return VariantResult("SPY", "screener", "h", 2, (), (), licences=lic)


def test_check_open_refuses_an_open_slice_that_joined_licensed_rows() -> None:
    from tests.unit.services.evaluation.time_series.test_sleeve import FIRST, LAST  # noqa: PLC0415

    def evaluation(*results: VariantResult):  # a minimal stand-in: only edge_id and results
        return type("E", (), {"edge_id": "e", "results": results})()

    open_ = SourceSlice(CBOE, FIRST, LAST)
    check_open(evaluation(_result("open")), open_)  # type: ignore[arg-type]
    with pytest.raises(AlgoTradeError, match="Cboe rows only"):
        check_open(evaluation(_result("personal")), open_)  # type: ignore[arg-type]
    history = replace(open_, source=OPTION_HISTORY)  # the history slice is meant to be personal
    check_open(evaluation(_result("personal")), history)  # type: ignore[arg-type]


def test_an_empty_in_sample_slice_does_not_crash_the_measures() -> None:
    """An open slice starting after the split has no in-sample session: its measures are empty."""
    in_sample = Slice("in_sample", "in_sample", lambda s: s.session < date(2025, 1, 1))
    (m,) = slice_measures([A, B], [in_sample])
    assert (m.sessions, m.picks) == (0, 0) and m.lift is None and m.sharpe is None
