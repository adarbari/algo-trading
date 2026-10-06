"""``MarketRegime`` (ADR 0047): the label, scores, indicators and sizing for exactly the session;
UNKNOWN with a reason while the groups do not exist or have no partition for it (an older
partition is never shown), and the headline templated from the indicators' counts."""

from dataclasses import replace

import pytest

from algotrade.config.site.regime.cards import load_cards
from algotrade.config.strategy.regime import DEFAULT_MULTIPLIERS
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.features import catalogue
from algotrade.services.read.instruments.catalogue import FeatureFormat
from algotrade.services.read.regime.fields import (
    FRAGILITY,
    MACRO_COVERAGE,
    MACRO_RISK,
    MARKET_COVERAGE,
    MARKET_STRESS,
)
from algotrade.services.read.regime.indicators import (
    IndicatorStatus,
    RegimeIndicator,
    RiskDirection,
)
from algotrade.services.read.regime.regime import (
    RegimeLabel,
    headline,
    load_regime,
)
from algotrade.services.read.values import UnknownCode
from algotrade.storage.configs.files import FileConfigStore
from tests.conftest import REPO_ROOT
from tests.unit.services.read.instruments.conftest import D0, D1, context, store_with
from tests.unit.services.read.regime.conftest import (
    SEP28,
    card,
    regime_ctx,
    with_regime,
    write_indicators,
    write_regime,
)


def test_the_regime_for_the_session() -> None:
    found = load_regime(regime_ctx())
    assert (found.session, found.label, found.plain_label) == (D1, RegimeLabel.STRESS, "Storm")
    assert found.unknown_reason is None
    assert found.scores.macro_risk.value == 62.5 and found.scores.market_stress.value == 71.0
    fragility = found.scores.fragility  # stored null: UNKNOWN with the reason, never 0
    assert fragility.value is None and fragility.unknown is not None
    assert fragility.unknown.code is UnknownCode.NULL
    assert (found.sizing.label, found.sizing.multiplier) == (RegimeLabel.STRESS, 0.5)
    assert found.headline == (
        "1 of 1 slow-moving warning signs are on. The fast signs are quiet. "
        "1 changed in the last 5 sessions."
    )


def test_each_indicator_is_a_card_joined_to_its_value() -> None:
    curve, hy, trend, vix = load_regime(regime_ctx()).indicators
    assert (curve.key, curve.pace, curve.plain_name) == ("curve", "slow", "Plain curve?")
    assert curve.technical_name == "curve (technical)" and curve.feature.endswith(".curve")
    assert (curve.value, curve.unknown, curve.format) == (-0.2, None, FeatureFormat.NUMBER)
    assert (curve.status, curve.changed) == (IndicatorStatus.ON, True)
    assert [(b.episode, b.line) for b in curve.before] == [
        ("2008", "curve rose."),
        ("2020", "curve jumped."),
    ]
    assert [(link.title, link.url) for link in curve.links] == [
        ("curve page", "https://example.org/curve")
    ]
    assert (trend.value, trend.status, trend.changed) == (0.9, IndicatorStatus.OFF, False)
    # a value without its verdict column: the value shows, the verdict is UNKNOWN (never derived)
    assert (vix.value, vix.status, vix.changed) == (1.1, IndicatorStatus.UNKNOWN, None)
    # a card whose feature is in no group yet
    assert hy.value is None and hy.format is None and hy.status is IndicatorStatus.UNKNOWN
    assert hy.unknown is not None and hy.unknown.code is UnknownCode.NOT_IN_CATALOGUE


def test_nothing_computed_yet_is_an_unknown_regime_not_an_error() -> None:
    ctx = replace(context(store_with()), configs=FileConfigStore(REPO_ROOT / "config"))
    found = load_regime(ctx)
    assert (found.label, found.plain_label) == (RegimeLabel.UNKNOWN, "Not computed yet")
    assert found.headline == "Not computed yet"
    assert found.unknown_reason is not None
    # the site catalogue has the RG3 groups: nothing stored for the session is NO_PARTITION
    assert found.unknown_reason.code is UnknownCode.NO_PARTITION
    scores = (found.scores.macro_risk, found.scores.market_stress, found.scores.fragility)
    assert all(s.value is None and s.unknown is not None for s in scores)
    assert (found.sizing.label, found.sizing.multiplier) == (RegimeLabel.UNKNOWN, None)
    assert [i.key for i in found.indicators] == [c.key for c in load_cards(ctx.configs).cards]
    assert len(found.indicators) == 8
    assert {i.status for i in found.indicators} == {IndicatorStatus.UNKNOWN}
    assert all(i.unknown is not None and i.value is None for i in found.indicators)


def test_a_session_with_no_partition_never_shows_an_older_one() -> None:
    # SEP28 and D0 are stored (CALM) but the session D0 has no regime partition of its own
    ctx = regime_ctx(D0)
    found = load_regime(ctx)
    assert found.session == D0 and found.label is RegimeLabel.UNKNOWN
    assert found.unknown_reason is not None
    assert found.unknown_reason.code is UnknownCode.NO_PARTITION
    assert str(D0) in found.unknown_reason.detail
    assert found.scores.macro_risk.value is None
    assert {i.status for i in found.indicators} == {IndicatorStatus.UNKNOWN}
    assert found.indicators[0].unknown is not None
    assert found.indicators[0].unknown.code is UnknownCode.NO_PARTITION
    assert SEP28 < D0  # an older CALM partition exists and is ignored


def test_a_label_outside_the_four_is_unknown_not_guessed() -> None:
    def odd(writer: object) -> None:
        write_regime(writer, D1, "SUNNY")

    found = load_regime(with_regime(context(store_with(odd))))
    assert found.label is RegimeLabel.UNKNOWN and found.unknown_reason is not None
    assert (
        found.unknown_reason.code is UnknownCode.NULL and "'SUNNY'" in found.unknown_reason.detail
    )


def test_a_null_label_is_unknown_with_the_stored_null() -> None:
    def null(writer: object) -> None:
        write_regime(writer, D1, None)

    found = load_regime(with_regime(context(store_with(null))))
    assert found.label is RegimeLabel.UNKNOWN and found.unknown_reason is not None
    assert found.unknown_reason.code is UnknownCode.NULL
    assert found.sizing.multiplier is None


def test_no_cards_is_a_regime_without_indicators() -> None:
    found = load_regime(with_regime(context(store_with(_labelled)), cards=[]))
    assert found.indicators == () and found.label is RegimeLabel.CALM
    assert (
        found.headline
        == "The slow-moving warning signs are not available. The fast signs are not available."
    )


def _labelled(writer: object) -> None:
    write_regime(writer, D1, "CALM")
    write_indicators(writer, D1, curve=1.0)


def test_sizing_comes_from_the_typed_regime_settings() -> None:
    """ADR 0049: the multipliers are ``RegimeSettings``' (``defaults.toml [regime]``); a label
    the file leaves out keeps the settings' default."""
    mult = {"CALM": 1, "CAUTION": 0.9, "STRESS": 0.6}
    ctx = with_regime(
        context(store_with(_labelled)),
        defaults={"regime": {"multipliers": mult}},
    )
    found = load_regime(ctx)
    assert (found.sizing.label, found.sizing.multiplier) == (RegimeLabel.CALM, 1.0)
    assert DEFAULT_MULTIPLIERS["CRISIS"] == 0.25  # the settings' default without a value
    assert load_regime(regime_ctx()).sizing.multiplier == 0.5


def test_a_bad_multiplier_names_its_path() -> None:
    bad = {"CALM": 1, "CAUTION": True}
    ctx = with_regime(context(store_with(_labelled)), defaults={"regime": {"multipliers": bad}})
    with pytest.raises(
        ConfigurationError, match=r"defaults.toml \[regime.multipliers\] CAUTION: expected"
    ):
        load_regime(ctx)
    over = {"CALM": 1.5}
    ctx = with_regime(context(store_with(_labelled)), defaults={"regime": {"multipliers": over}})
    with pytest.raises(ConfigurationError, match="CALM: expected a fraction between 0 and 1"):
        load_regime(ctx)


def _ind(pace: str, status: IndicatorStatus, changed: bool | None = None) -> RegimeIndicator:
    ind = load_regime(regime_ctx()).indicators[0]
    return RegimeIndicator(**{**ind.__dict__, "pace": pace, "status": status, "changed": changed})


def test_the_headline_counts_only_known_verdicts() -> None:
    on, off, unknown = IndicatorStatus.ON, IndicatorStatus.OFF, IndicatorStatus.UNKNOWN
    items = (_ind("slow", on), _ind("slow", off), _ind("slow", unknown), _ind("fast", on, True))
    assert headline(RegimeLabel.CAUTION, items) == (
        "1 of 2 slow-moving warning signs are on. 1 of 1 fast signs are on. "
        "1 changed in the last 5 sessions."
    )
    assert headline(RegimeLabel.UNKNOWN, items) == "Not computed yet"
    assert headline(RegimeLabel.CALM, (_ind("slow", off, False),)) == (
        "0 of 1 slow-moving warning signs are on. The fast signs are not available."
    )


def _screen(config_id: str, name: str, **extra: object) -> dict[str, object]:
    return {
        "id": config_id, "kind": "screener", "impl": "rules", "version": 1, "name": name,
        "selection": "all_active",
        "criteria": {"price": {"field": "rollup.price_stats@v2.close", "op": "gt", "value": 5,
                               "mode": "hard"}},
        **extra,
    }  # fmt: skip


SELECTION = {
    ("site", "selections", "all_active"): {
        "name": "all_active",
        "where": {"all": [{"field": "instrument.status", "op": "eq", "value": "ACTIVE"}]},
    },
}
GATED = {
    "regime": {
        "enabled": True,
        "pause_in": ["CRISIS"],
        "unknown_multiplier": 0.1,
        "screeners": {"vrp_scanner": {"pause_in": ["STRESS", "CRISIS"]}},
    }
}


def test_sizing_carries_the_multipliers_the_unknown_size_and_each_screeners_pauses() -> None:
    docs = {
        **SELECTION,
        ("site", "screeners", "vrp_scanner@1"): _screen("vrp_scanner", "VRP scanner"),
        ("site", "screeners", "momentum@1"): _screen("momentum", "Momentum"),
    }
    sizing = load_regime(with_regime(regime_ctx(), defaults=GATED, docs=docs, user="me")).sizing
    assert sizing.enabled and sizing.unknown_multiplier == 0.1
    assert [(m.label.value, m.multiplier) for m in sizing.multipliers] == [
        ("CALM", 1.0), ("CAUTION", 0.75), ("STRESS", 0.5), ("CRISIS", 0.25)
    ]  # fmt: skip
    gates = [(g.screener_id, g.name, g.enabled, [p.value for p in g.pause_in])
             for g in sizing.screeners]  # fmt: skip
    assert gates == [
        ("momentum", "Momentum", True, ["CRISIS"]),
        ("vrp_scanner", "VRP scanner", True, ["STRESS", "CRISIS"]),
    ]  # fmt: skip


def test_a_users_own_regime_layer_changes_their_screeners_pauses_only() -> None:
    docs = {
        **SELECTION,
        ("site", "screeners", "momentum@1"): _screen("momentum", "Momentum"),
        ("me", "screeners", "momentum@2"): _screen(
            "momentum", "My momentum", regime={"enabled": True, "pause_in": ["CAUTION"]}
        ),
    }
    mine = load_regime(with_regime(regime_ctx(), docs=docs, user="me")).sizing
    assert mine.enabled  # site gate off, the user's own turned it on for their screener
    assert [(g.name, g.enabled, [p.value for p in g.pause_in]) for g in mine.screeners] == [
        ("My momentum", True, ["CAUTION"])
    ]  # fmt: skip
    other = load_regime(with_regime(regime_ctx(), docs=docs, user="you")).sizing
    assert not other.enabled  # another user sees the site's preset: the gate is off
    assert [(g.name, g.enabled) for g in other.screeners] == [("Momentum", False)]


def test_the_gate_off_by_default_says_so() -> None:
    sizing = load_regime(regime_ctx()).sizing
    assert not sizing.enabled and sizing.screeners == ()


def test_an_indicator_carries_its_range_linked_how_and_the_codes_rule() -> None:
    rollups = {"regime_indicators@v1": {"nfci_above": 0.25}, "regime@v3": {"macro_high": 40.0}}
    cards = [card("nfci", "slow"), card("breadth_200d", "fast"), card("hy", "slow")]
    ctx = with_regime(context(store_with()), cards, docs={("site", "settings", "rollups"): rollups})
    found = load_regime(ctx)
    nfci, breadth, hy = found.indicators
    assert (nfci.range.min, nfci.range.max) == (0, 1)
    assert [(p.text, p.url) for p in nfci.how] == [
        ("How ", None), ("nfci", "https://example.org/nfci/how"), (" is computed.", None)
    ]  # fmt: skip
    assert (nfci.threshold, nfci.direction) == (0.25, RiskDirection.HIGHER_IS_RISK)  # the site's
    assert (breadth.threshold, breadth.direction) == (0.4, RiskDirection.LOWER_IS_RISK)
    assert nfci.verdict_feature == "market.regime_indicators@v1.nfci_on"
    assert (hy.threshold, hy.direction) == (None, None)  # no rule in code for this key
    assert nfci.sources == () and hy.sources == ()  # the test group's columns have no inputs
    scores = found.scores
    macro, market, fragility = scores.macro_risk, scores.market_stress, scores.fragility
    assert (macro.feature, macro.coverage_feature, macro.threshold) == (
        "market.regime@v3.macro_risk", "market.regime@v3.macro_coverage", 40.0
    )  # fmt: skip
    assert (market.coverage_feature, market.threshold) == ("market.regime@v3.market_coverage", 50.0)
    assert (fragility.feature, fragility.coverage_feature, fragility.threshold) == (
        "market.regime@v3.fragility", None, None
    )  # fmt: skip


def test_the_score_fields_are_in_the_shipped_catalogue() -> None:
    market = catalogue(FileConfigStore(REPO_ROOT / "config")).field_types("market")
    for name in (MACRO_RISK, MARKET_STRESS, FRAGILITY, MACRO_COVERAGE, MARKET_COVERAGE):
        assert name in market, name
