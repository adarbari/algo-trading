"""The vocabulary of "not available" (ADR 0056): kinds are public and generic, a cause is the
admin's chain, and the kind of a value comes from its code alone."""

import pytest

from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.services.read.availability.cause import (
    GENERIC_REASONS,
    GUIDE_TERMS,
    Cause,
    CauseLevel,
    CauseLink,
    UnavailableKind,
    feature_cause,
    names_a_table,
    run_cause,
    table_cause,
)
from algotrade.services.read.values import KIND_OF_CODE, Unknown, UnknownCode
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT


def test_every_unknown_code_has_a_kind() -> None:
    assert set(KIND_OF_CODE) == set(UnknownCode)


def test_a_failure_is_system_and_a_missing_row_is_not_stored() -> None:
    assert KIND_OF_CODE[UnknownCode.NO_PARTITION] is UnavailableKind.SYSTEM
    assert KIND_OF_CODE[UnknownCode.NO_ROW] is UnavailableKind.NOT_STORED
    assert KIND_OF_CODE[UnknownCode.NULL] is UnavailableKind.NOT_STORED
    assert KIND_OF_CODE[UnknownCode.NOT_RUN] is UnavailableKind.NOT_RUN


@pytest.mark.parametrize("kind", list(UnavailableKind))
def test_the_public_words_name_no_table_vendor_or_step(kind: UnavailableKind) -> None:
    assert not names_a_table(GENERIC_REASONS[kind]) and GUIDE_TERMS[kind]


def test_a_cause_reads_root_first_and_finds_its_links() -> None:
    cause = Cause(
        (
            CauseLink(CauseLevel.SOURCE, "ibkr-iv", "UNAVAILABLE", "IB Gateway unreachable"),
            CauseLink(CauseLevel.STEP, "ibkr-iv", "SKIPPED", "skipped"),
            table_cause("rollups/x@v1", "no rows").leaf,
        )
    )
    assert cause.text == "IB Gateway unreachable -> skipped -> no rows"
    assert cause.leaf.level is CauseLevel.TABLE
    assert cause.first(CauseLevel.STEP) is cause.links[1] and cause.first(CauseLevel.RUN) is None


def test_the_leaf_helpers_build_one_link() -> None:
    assert feature_cause("f", "m", "NULL").leaf.level is CauseLevel.FEATURE
    assert run_cause("s", "m").leaf.status == "NOT_RUN"


def test_an_unknown_serves_its_public_words_without_the_cause() -> None:
    unknown = Unknown(UnknownCode.NO_PARTITION, table_cause("rollups/x@v1", "no partition"))
    assert unknown.public_reason == "not available because of a system error"
    assert "rollups" not in unknown.public_reason


def test_every_kind_has_a_glossary_term() -> None:
    """The Guide explains each public kind (ADR 0056): its term exists in the shipped glossary."""
    written = {t.id for t in load_guide_glossary(FileConfigStore(REPO_ROOT / "config")).terms}
    assert {k: v for k, v in GUIDE_TERMS.items() if v not in written} == {}
    assert set(GUIDE_TERMS) == set(UnavailableKind)
