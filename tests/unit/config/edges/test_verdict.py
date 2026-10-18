"""The verdict thresholds: defaults are the owner's, a bad value names the file and key."""

import tomllib
from pathlib import Path

import pytest

from algotrade.config.edges.verdict import KEYS, LEGS, VerdictSettings
from algotrade.core.model.errors import ConfigurationError


def test_defaults_are_the_owners_thresholds() -> None:
    d = VerdictSettings.from_document(None)
    assert (d.min_oos_trades, d.works_trades, d.works_oos_trades) == (40, 100, 40)
    assert (d.not_working_t, d.promising_t, d.works_t) == (1.0, 2.0, 3.0)
    assert (d.not_working_dsr, d.promising_dsr, d.works_dsr) == (0.5, 0.8, 0.95)
    assert (d.max_pbo, d.works_max_pbo, d.oos_lift_share) == (0.5, 0.2, 0.5)
    assert (d.forward_sessions, d.live_min_sessions, d.live_low, d.live_high) == (20, 10, 0.1, 0.9)
    assert d.cost_levels_bps == (0.0, 15.0, 30.0, 50.0)  # ADR 0064 (owner 2026-10-10)


def test_the_capacity_floor_defaults_reads_and_rejects_a_bad_value() -> None:
    assert VerdictSettings.from_document(None).capacity_adv_floor_usd == 5_000_000.0
    assert (
        VerdictSettings.from_document({"capacity_adv_floor_usd": 1e6}).capacity_adv_floor_usd == 1e6
    )
    for bad in (0, -1, "5e6", True):
        with pytest.raises(ConfigurationError, match="capacity_adv_floor_usd"):
            VerdictSettings.from_document({"capacity_adv_floor_usd": bad})


def test_the_capacity_position_defaults_reads_and_rejects_a_bad_value() -> None:
    assert VerdictSettings.from_document(None).capacity_position_usd == 100_000.0
    read = VerdictSettings.from_document({"capacity_position_usd": 250_000})
    assert read.capacity_position_usd == 250_000.0
    for bad in (0, -1, "1e5", True):
        with pytest.raises(ConfigurationError, match="capacity_position_usd"):
            VerdictSettings.from_document({"capacity_position_usd": bad})


@pytest.mark.parametrize("levels", [[15, 0], [0, 0], [-5], ["10"], [True], 10])
def test_the_cost_grid_is_distinct_non_negative_and_ascending(levels: object) -> None:
    with pytest.raises(ConfigurationError, match="levels_bps"):
        VerdictSettings.from_document({"edge_costs": {"levels_bps": levels}})


def test_the_cost_grid_reads_from_its_table() -> None:
    doc = {"edge_costs": {"levels_bps": [0, 10.5]}}
    assert VerdictSettings.from_document(doc).cost_levels_bps == (0.0, 10.5)
    assert VerdictSettings.from_document({"edge_costs": {}}).cost_levels_bps == (0, 15, 30, 50)
    with pytest.raises(ConfigurationError, match="unknown keys"):
        VerdictSettings.from_document({"edge_costs": {"floor": 1}})


def test_a_document_overrides_and_an_unknown_key_fails() -> None:
    assert VerdictSettings.from_document({"min_oos_trades": 60}).min_oos_trades == 60
    with pytest.raises(ConfigurationError, match="unknown keys"):
        VerdictSettings.from_document({"min_trade": 1})
    with pytest.raises(ConfigurationError, match="max_pbo"):
        VerdictSettings.from_document({"max_pbo": 2})
    with pytest.raises(ConfigurationError, match="live_low"):
        VerdictSettings.from_document({"live_low": 1.5})


def test_the_committed_file_parses_to_the_defaults() -> None:
    doc = tomllib.loads(Path("config/site/verdict.toml").read_text())
    assert VerdictSettings.from_document(doc) == VerdictSettings()


def test_works_needs_the_picks_t_too_and_the_published_haircut_has_its_two_legs() -> None:
    d = VerdictSettings.from_document(None)
    assert (d.works_t, d.works_picks_t) == (3.0, 3.0)  # owner 2026-10-17
    assert (d.haircut_long_short, d.haircut_long) == (0.5, 0.333)
    assert d.published_haircut("long_short") == 0.5 and d.published_haircut("long") == 0.333
    read = VerdictSettings.from_document({"published_haircut": {"long": 0.25}})
    assert (read.haircut_long, read.haircut_long_short) == (0.25, 0.5)
    for bad in ({"long": 1.5}, {"long_short": -0.1}, {"long_short": "half"}):
        with pytest.raises(ConfigurationError, match="long"):
            VerdictSettings.from_document({"published_haircut": bad})
    with pytest.raises(ConfigurationError, match="unknown keys"):
        VerdictSettings.from_document({"published_haircut": {"short_only": 0.5}})


def test_every_key_of_the_verdict_file_is_read_and_every_read_key_is_in_the_file() -> None:
    """Fitness: a threshold added to ``KEYS`` is written in ``verdict.toml`` (with its comment),
    and a key in the file is one the loader reads (an unknown one already fails to load)."""
    doc = tomllib.loads(Path("config/site/verdict.toml").read_text())
    assert set(doc) == set(KEYS)
    assert set(doc["published_haircut"]) == set(LEGS)
    assert set(doc["edge_costs"]) == {"levels_bps", "borrow_bps_annual"}


def test_the_assumed_borrow_cost_defaults_reads_and_rejects_a_bad_value() -> None:
    assert VerdictSettings.from_document(None).borrow_bps_annual == 100.0
    read = VerdictSettings.from_document({"edge_costs": {"borrow_bps_annual": 250}})
    assert read.borrow_bps_annual == 250.0
    assert read.cost_levels_bps == (0.0, 15.0, 30.0, 50.0)  # the grid keeps its default
    for bad in (-1, "100", True):
        with pytest.raises(ConfigurationError, match="borrow_bps_annual"):
            VerdictSettings.from_document({"edge_costs": {"borrow_bps_annual": bad}})


def test_a_short_leg_has_its_own_published_haircut_beside_the_others() -> None:
    d = VerdictSettings.from_document(None)
    assert (d.published_haircut("short"), d.published_haircut("long_short")) == (0.5, 0.5)
    assert d.published_haircut("long") == 0.333
    read = VerdictSettings.from_document({"published_haircut": {"short": 0.4}})
    assert read.published_haircut("short") == 0.4 and read.published_haircut("long_short") == 0.5


def test_the_standard_decoys_default_read_and_reject_a_bad_list() -> None:
    standard = VerdictSettings.from_document(None).decoys_standard
    assert standard[:2] == ("size_small", "momentum_12_1") and len(standard) == 6
    read = VerdictSettings.from_document({"decoys": {"standard": ["size_small", "beta_low"]}})
    assert read.decoys_standard == ("size_small", "beta_low")
    for bad in (["a", "a"], [1], "size_small"):
        with pytest.raises(ConfigurationError, match="standard"):
            VerdictSettings.from_document({"decoys": {"standard": bad}})
    with pytest.raises(ConfigurationError, match="invalid screener id"):
        VerdictSettings.from_document({"decoys": {"standard": ["Not An Id"]}})
    with pytest.raises(ConfigurationError, match="decoys"):
        VerdictSettings.from_document({"decoys": {"typo": []}})
