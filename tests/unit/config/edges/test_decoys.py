"""Fitness test over the shipped ``config/site/verdict.toml [decoys]`` (ADR 0053 amendment
2026-10-18): every decoy the standard battery names is a site rule-screen preset with its Guide
playbook (the Guide says what a decoy ranks by before an edge is compared with it), and ranks
by something (a decoy is a ranking)."""

import tomllib

import pytest

from algotrade.config.edges.verdict import DECOYS_STANDARD, VerdictSettings
from algotrade.config.site.guide.playbooks import FOLDER, load_guide_playbooks
from algotrade.config.user import SITE_USER, UserContext
from algotrade.services.configs import resolve_config
from algotrade.storage.configs.files import SCREENERS, FileConfigStore
from tests.conftest import REPO_ROOT

SHIPPED = FileConfigStore(REPO_ROOT / "config")
STANDARD = VerdictSettings.from_document(
    tomllib.loads((REPO_ROOT / "config/site/verdict.toml").read_text())
).decoys_standard


def test_the_committed_standard_list_is_the_default_and_has_the_six_decoys() -> None:
    assert STANDARD == DECOYS_STANDARD
    assert set(STANDARD) >= {
        "size_small", "momentum_12_1", "ivol_high", "max_ret_high", "amihud_illiquid", "beta_low",
    }  # fmt: skip


@pytest.mark.parametrize("decoy", STANDARD)
def test_every_standard_decoy_is_a_site_preset(decoy: str) -> None:
    assert decoy in SHIPPED.names("site", SCREENERS), (
        f"verdict.toml [decoys] names {decoy!r}: add config/site/presets/screeners/{decoy}/v1.toml"
    )


@pytest.mark.parametrize("decoy", STANDARD)
def test_every_standard_decoy_has_a_guide_playbook(decoy: str) -> None:
    assert load_guide_playbooks(SHIPPED).get(decoy) is not None, (
        f"verdict.toml [decoys] names {decoy!r}: write config/site/guide/playbooks/<family>/"
        f"{decoy}.toml ({FOLDER}) so the Guide says what the decoy ranks by"
    )


@pytest.mark.parametrize("decoy", STANDARD)
def test_every_standard_decoy_ranks_by_something(decoy: str) -> None:
    spec = resolve_config(SHIPPED, decoy, UserContext(SITE_USER)).screen_spec
    assert spec.tie_break, f"{decoy} ranks by nothing: a decoy is a ranking"
