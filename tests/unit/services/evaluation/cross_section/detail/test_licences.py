"""The licence of a trial and of its ledger columns (ADR 0064 decision 10): the strictest
catalogue licence of what each is derived from; a field the catalogue does not know is open."""

from algotrade.config.strategy.schema import parse_selection
from algotrade.config.user import UserContext
from algotrade.services.configs import resolve_config
from algotrade.services.evaluation.cross_section.detail.licences import (
    screen_fields,
    trial_licences,
)
from algotrade.services.features import catalogue
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.evaluation.cross_section.conftest import ACTIVE, PRICE, edge, screen

IBKR = "rollup.ibkr_iv@v1.iv30_ibkr"  # a personal-licence feature (ADR 0028)
USER = UserContext("site")


def configs(tie_break: str) -> MemoryConfigStore:
    doc = {**screen(), "rank": {"tie_break": tie_break, "tie_break_order": "desc"}}
    return MemoryConfigStore(
        {("site", "selections", "active"): ACTIVE, ("site", "strategies", "momo"): doc}
    )


def licences(tie_break: str, iv: str | None):  # type: ignore[no-untyped-def]
    store = configs(tie_break)
    resolved = resolve_config(store, "momo", USER)
    universe = parse_selection(ACTIVE, "active")
    return trial_licences(catalogue(store, "site"), edge(), universe, resolved, iv)


def test_an_open_trial_has_open_columns() -> None:
    found = licences(PRICE, None)
    assert (found.trial, found.value, found.score, found.adv) == ("open",) * 4


def test_a_screen_reading_a_personal_feature_makes_the_score_and_the_trial_personal() -> None:
    found = licences(IBKR, None)
    assert (found.trial, found.score, found.value) == ("personal", "personal", "open")
    assert IBKR in screen_fields(resolve_config(configs(IBKR), "momo", USER), edge())


def test_a_personal_implied_vol_makes_the_value_and_the_trial_personal() -> None:
    found = licences(PRICE, "personal")
    assert (found.trial, found.value, found.score) == ("personal", "personal", "open")
