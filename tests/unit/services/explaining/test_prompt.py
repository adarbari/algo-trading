"""The explanation prompt (ADR 0041, amended): byte-stable over the same regime, the facts only
(what is on or changed, the card asked about in full), the allowed links, the question as the
user text."""

from dataclasses import replace

from algotrade.services.explaining.prompt import (
    TASK,
    WHAT_IS_HAPPENING,
    regime_facts,
    shown,
    system_prompt,
    user_prompt,
)
from algotrade.services.read.instruments.catalogue import FeatureFormat
from algotrade.services.read.regime.indicators import IndicatorStatus
from algotrade.services.read.regime.regime import MarketRegime

FACTS = """\
The market's weather: Storm. 1 of 1 slow-moving warning signs are on. The fast signs are quiet. 1 changed in the last 5 sessions.
Scores:
- Slow-warning score (macro risk, moves over weeks): 62 out of 100
- Market stress score (trend, volatility, breadth, moves daily): 71 out of 100
- Fragility (context only: how deep a fall from here could be): not available
Warning signs that are on or changed:
- Plain curve? What curve measures. Pace: slow-moving. Value now: -0.2. Warning sign: on. It changed in the last 5 sessions.
  Lead time: Months. Track record: Some."""  # noqa: E501


def test_the_facts_are_byte_stable_and_only_what_is_on_or_changed(regime: MarketRegime) -> None:
    facts = regime_facts(regime)
    assert facts.text == FACTS
    assert regime_facts(regime) == facts
    assert facts.as_of == "As of 2026-10-01."  # shown to the model, not a quotable number
    assert [(link.title, link.url) for link in facts.links] == [
        ("curve page", "https://example.org/curve")
    ]


def test_the_system_prompt_is_the_task_the_facts_and_the_allowed_links(
    regime: MarketRegime,
) -> None:
    system = system_prompt(regime_facts(regime))
    assert system == (
        f"{TASK}\nFACTS\nAs of 2026-10-01.\n{FACTS}\n\nALLOWED LINKS\n- curve page: https://example.org/curve\n"
    )
    assert "describe what is happening; never advise" in system.lower()
    assert "under 150 words" in system.lower() and "no markdown" in system.lower()
    assert user_prompt(WHAT_IS_HAPPENING) == "what is happening?"


def test_a_card_question_adds_that_card_in_full(regime: MarketRegime) -> None:
    trend = regime.indicators[2]  # off and unchanged: not in the plain facts
    assert "Plain trend?" not in regime_facts(regime).text
    facts = regime_facts(regime, trend)
    assert "- Plain trend? What trend measures. Pace: fast-moving. Value now: 0.9." in facts.text
    assert "  Why it matters: Why trend matters." in facts.text
    assert "  What on means: trend is on when high." in facts.text
    assert "  Before 2008: trend rose." in facts.text
    assert [link.url for link in facts.links] == [
        "https://example.org/curve",
        "https://example.org/trend",
    ]


def test_nothing_on_or_changed_says_so_and_allows_no_links(regime: MarketRegime) -> None:
    quiet = replace(
        regime,
        indicators=tuple(
            replace(i, status=IndicatorStatus.OFF, changed=False) for i in regime.indicators
        ),
    )
    facts = regime_facts(quiet)
    assert "No warning sign is on and none changed in the last 5 sessions." in facts.text
    assert facts.links == ()
    assert system_prompt(facts).endswith("ALLOWED LINKS\n- none\n")


def test_the_prompt_carries_no_user_data_or_credentials(regime: MarketRegime) -> None:
    system = system_prompt(regime_facts(regime))
    for forbidden in ("sk-", "Bearer", "api_key", "@"):
        assert forbidden not in system


def test_a_value_is_shown_as_a_reader_sees_it(regime: MarketRegime) -> None:
    curve = regime.indicators[0]
    known = replace(curve, value=0.0132, format=FeatureFormat.PERCENT)
    assert shown(known) == "1.3%"
    assert shown(replace(curve, value=12.5, format=FeatureFormat.CURRENCY)) == "$12.5"
    assert shown(replace(curve, value=13900000000.0, format=FeatureFormat.COMPACT)) == (
        "13,900,000,000"
    )
    assert shown(replace(curve, value=True, format=FeatureFormat.FLAG)) == "yes"
    assert shown(replace(curve, value="HIGH", format=FeatureFormat.CATEGORY)) == "HIGH"
    assert shown(regime.indicators[1]) == "not available"  # hy: in no group
