"""The contract between the chains acceptance check and the screens (ADR 0054): the stale
chains the gate tolerates are EXCLUDED from a screen's coverage, never a pick; one stale name
more than it tolerates and the gate FAILS and the screen is PARTIAL again. Both read the same
status frame through ``data.chains`` (the gate through ``stale_in_tier``, the screen through
``tolerated_stale``), so they cannot drift.

The exact limits are ``max_chain_stale_share_core`` 2% and ``max_chain_stale_share`` 20%:
50 core names tolerate 1 stale, 50 rest names tolerate 10."""

from datetime import date

import pytest

from algotrade.config.site.settings import SourcesSettings
from algotrade.config.strategy.resolve import ResolvedConfig
from algotrade.config.user import SITE_USER, UserContext
from algotrade.data.chains import STALE_REASON, chain_status, tolerated_stale
from algotrade.engines.screening.runner import RunCoverage
from algotrade.services.configs import resolve_config
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


def screened(core_stale: int, rest_stale: int, sources: SourcesSettings | None = SOURCES):
    reader, writer = seed_chain_screen(DAY, chain_status_rows(50, core_stale, 50, rest_stale))
    return reader, run_screener(reader, writer, preset(), DAY, now=T0, sources=sources)


def test_stale_names_at_the_gates_limits_are_excluded_and_the_run_is_complete() -> None:
    reader, outcome = screened(core_stale=1, rest_stale=10)
    run = outcome.run
    assert len(tolerated_stale(chain_status(reader, DAY), SOURCES)) == 11
    assert run.coverage is RunCoverage.COMPLETE
    assert (run.excluded, run.processed, run.coverage_pct) == (11, 89, 1.0)
    assert outcome.audit["excluded"] == 11 and outcome.audit["skipped"] == 0
    assert outcome.audit["excluded_reasons"] == {STALE_REASON: 11}
    stale = [r for r in run.rows if r.decision is Decision.EXCLUDED]
    assert {r.instrument_id for r in stale} == {
        *(f"EQ:C{i}" for i in range(1)),
        *(f"EQ:R{i}" for i in range(10)),
    }
    assert all(r.reasons[0] == STALE_REASON for r in stale)  # then the screener's own reason
    saved = reader.table("results/short_premium_liquidity", DAY)
    assert saved is not None
    assert set(
        saved.loc[saved["instrument_id"].isin([r.instrument_id for r in stale]), "decision"]
    ) == {"EXCLUDED"}


@pytest.mark.parametrize(("core_stale", "rest_stale"), [(2, 10), (1, 11), (0, 11), (3, 0)])
def test_one_more_stale_name_than_the_gate_tolerates_is_partial_again(
    core_stale: int, rest_stale: int
) -> None:
    reader, outcome = screened(core_stale, rest_stale)
    assert tolerated_stale(chain_status(reader, DAY), SOURCES) == {}  # the gate FAILED
    assert outcome.run.coverage is RunCoverage.PARTIAL
    assert outcome.run.excluded == 0 and outcome.audit["excluded"] == 0


def test_without_the_sources_nothing_is_excluded() -> None:
    _, outcome = screened(core_stale=1, rest_stale=10, sources=None)
    assert outcome.run.coverage is RunCoverage.PARTIAL  # 89 of 100: below the 98% minimum
    assert outcome.run.excluded == 0
