"""Every calendar window an edge schedule may use has its own Guide term, ``calendar_<window>``
(ADR 0051, ADR 0053): ``edge.schedule`` is a plain String, so ``guide_coverage.toml`` cannot map
its values; this test keeps the closed set of windows and the Guide in step, and the length a
window declares is the one horizon a document may give it."""

import pytest

from algotrade.config.site.guide.glossary import load_guide_glossary
from algotrade.core.time.windows import WINDOW_LENGTHS, WINDOW_NAMES
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT


def test_every_window_name_has_its_own_guide_term() -> None:
    terms = {t.id for t in load_guide_glossary(FileConfigStore(REPO_ROOT / "config")).terms}
    missing = [f"calendar_{w}" for w in WINDOW_NAMES if f"calendar_{w}" not in terms]
    assert not missing, f"write a glossary term in config/site/guide/glossary/edges/: {missing}"
    assert "base_out_of_window" in terms  # the base of a time-series edge (ADR 0073)
    stray = sorted(t for t in terms if t.startswith("calendar_") and t[9:] not in WINDOW_NAMES)
    assert not stray, f"a calendar_ term for no window: {stray}"


@pytest.mark.parametrize("name", WINDOW_NAMES)
def test_a_window_declares_a_positive_length(name: str) -> None:
    assert WINDOW_LENGTHS[name] >= 1
