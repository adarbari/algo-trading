"""The contract between the chains acceptance check and the screens (ADR 0054, ADR 0088 S5):
a stale chain is never a pick. The gate decides how many stale names it tolerates (through
``stale_in_tier``, the screen's ``tolerated_stale`` reads the same status frame, so they cannot
drift); a screen over option_liquidity is a rule screen since S5, which decides every name
(a name with no usable tier is a REJECT, ADR 0030), so a stale name is a reject in the run and
the chains step, not the screen's coverage, is what fails when too many are stale.

The exact limits are ``max_chain_stale_share_core`` 2% and ``max_chain_stale_share`` 20%:
50 core names tolerate 1 stale, 50 rest names tolerate 10."""

from datetime import date

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import SITE_USER, UserContext
from algotrade.data.chains import chain_status, tolerated_stale
from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.configs import resolve_config
from algotrade.services.licences import HARNESS_ALL
from algotrade.services.screening.run import run_screener
from algotrade.storage.configs.files import FileConfigStore
from algotrade.strategies.screeners.base import Decision
from tests.conftest import REPO_ROOT
from tests.helpers.stored_frames import T0, chain_status_rows, seed_chain_screen

DAY = date(2026, 10, 2)
SOURCES = SourcesSettings()  # the site defaults: 2% core, 20% rest
SITE_CONFIGS = FileConfigStore(REPO_ROOT / "config")


def preset() -> ResolvedConfig:
    return resolve_config(SITE_CONFIGS, "short_premium_liquidity", UserContext(SITE_USER))


def screened(
    core_stale: int,
    rest_stale: int,
    sources: SourcesSettings | None = SOURCES,
    chain_day: str = "2026-10-01",
):
    rows = chain_status_rows(50, core_stale, 50, rest_stale, chain_day=chain_day)
    reader, writer = seed_chain_screen(DAY, rows)
    return reader, run_screener(
        reader, writer, preset(), DAY, now=T0, sources=sources, held=HARNESS_ALL
    )


def test_stale_names_are_rejected_never_picked() -> None:
    reader, outcome = screened(core_stale=1, rest_stale=10)
    run = outcome.run
    assert len(tolerated_stale(chain_status(reader, DAY), DAY, SOURCES)) == 11
    assert run.coverage is RunCoverage.COMPLETE
    stale_ids = {*(f"EQ:C{i}" for i in range(1)), *(f"EQ:R{i}" for i in range(10))}
    rows = {r.instrument_id: r for r in run.rows}
    assert all(rows[i].decision is Decision.REJECT for i in stale_ids)
    saved = reader.table("results/rule_screen", DAY)
    assert saved is not None
    assert set(saved.loc[saved["instrument_id"].isin(stale_ids), "decision"]) == {"REJECT"}


@pytest.mark.parametrize(("core_stale", "rest_stale"), [(2, 10), (1, 11), (0, 11), (3, 0)])
def test_one_more_stale_name_than_the_gate_tolerates_fails_the_gate(
    core_stale: int, rest_stale: int
) -> None:
    reader, outcome = screened(core_stale, rest_stale)
    assert tolerated_stale(chain_status(reader, DAY), DAY, SOURCES) == {}  # the gate FAILED
    assert outcome.run.excluded == 0 and outcome.audit["excluded"] == 0


def test_chronically_stale_chains_are_never_tolerated() -> None:
    """Stale for more than ``max_chain_stale_sessions`` (5): fetch failures, 11 of 100 over the
    2% limit, so the gate FAILS and nothing is tolerated."""
    reader, outcome = screened(core_stale=1, rest_stale=10, chain_day="2026-09-24")
    assert tolerated_stale(chain_status(reader, DAY), DAY, SOURCES) == {}
    assert outcome.run.excluded == 0


def test_without_the_sources_nothing_is_excluded() -> None:
    _, outcome = screened(core_stale=1, rest_stale=10, sources=None)
    assert outcome.run.excluded == 0
