"""The prompt a regime explanation is asked with (ADR 0041, amended 2026-10-06): the task, then
the facts block and the allowed links, and the question as the user text. The facts are the
regime's plain label and headline, its three scores, and each indicator that is on or changed
(plain name, one line, value, verdict, lead time, false-alarm line); for a card question, that
card in full (why it matters, what "on" means, what it did before). The allowed links are the
cards' reading lists. No market data beyond these numbers, no user data, no credentials, no free
text from the page. Rendered with no timestamps or ids, so the same regime gives the same bytes
(a provider's prompt cache hits and a recorded test stays valid)."""

from dataclasses import dataclass

from algotrade.services.read.instruments.catalogue import FeatureFormat
from algotrade.services.read.regime.indicators import IndicatorStatus, RegimeIndicator
from algotrade.services.read.regime.regime import MarketRegime, RegimeScore

WHAT_IS_HAPPENING = "what is happening?"
# Bump when the facts' wording or layout changes (the task text is hashed on its own): cached
# answers are keyed by it, so a changed prompt never serves an answer to the old one.
PROMPT_VERSION = 1

TASK = """\
You explain the state of the stock market to someone who does not follow markets. The facts
below are everything you may use: the market's weather today and the warning signs behind it.

Rules:
- Describe what is happening; never advise. Do not say what to buy, sell, hold or do.
- Use only the facts and links given. Do not add numbers, dates, events or causes of your own.
  Every number you write must appear in the facts.
- Name the one or two signals that matter most, in the plain words of the facts.
- Under 150 words, plain text, no markdown, no lists, no headings.
- Write a number exactly as the facts do, with its sign: a fall to -3.2 is "-3.2", never "3.2".
- Cite a link only when you used it, and only from the allowed links, spelled exactly.

Answer with ONE JSON object and nothing else (no code fence):
{"text": "<your explanation>", "links": ["<an allowed url>", ...]}
"""


@dataclass(frozen=True)
class Link:
    """One allowed link: what it is and where it goes."""

    title: str
    url: str


@dataclass(frozen=True)
class Facts:
    """What the model may use: ``text`` (every number the answer may quote is in it), the
    ``as_of`` line (the session's date, shown to the model but not a quotable number) and the
    ``links`` it may cite, in a stable order."""

    text: str
    links: tuple[Link, ...]
    as_of: str = ""


def _trim(number: float, places: int) -> str:
    return f"{number:,.{places}f}".rstrip("0").rstrip(".") if places else f"{number:,.0f}"


def shown(indicator: RegimeIndicator) -> str:
    """The indicator's value as a reader sees it (``not available`` when it is unknown)."""
    value = indicator.value
    if indicator.unknown is not None or value is None:
        return "not available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if not isinstance(value, int | float):
        return str(value)
    if indicator.format is FeatureFormat.PERCENT:
        return f"{_trim(value * 100, 1)}%"
    if indicator.format is FeatureFormat.CURRENCY:
        return f"${_trim(value, 2)}"
    return _trim(value, 0 if indicator.format is FeatureFormat.COMPACT else 2)


def _score(label: str, score: RegimeScore) -> str:
    return (
        f"- {label}: {_trim(score.value, 0)} out of 100"
        if score.value is not None
        else (f"- {label}: not available")
    )


def _signal(indicator: RegimeIndicator, detailed: bool) -> list[str]:
    changed = " It changed in the last 5 sessions." if indicator.changed else ""
    lines = [
        f"- {indicator.plain_name} {indicator.one_liner} Pace: {indicator.pace}-moving. "
        f"Value now: {shown(indicator)}. Warning sign: {indicator.status.value.lower()}.{changed}",
        f"  Lead time: {indicator.lead_time} Track record: {indicator.false_alarms}",
    ]
    if detailed:
        lines.append(f"  Why it matters: {indicator.why_it_matters}")
        lines.append(f"  What on means: {indicator.what_on_means}")
        lines += [f"  Before {e.episode}: {e.line}" for e in indicator.before]
    return lines


def regime_facts(regime: MarketRegime, card: RegimeIndicator | None = None) -> Facts:
    """The facts for ``regime``: every indicator that is on or changed, and ``card`` (one of
    the regime's indicators, a card question) in full. The links are those of the indicators
    shown, once each, in card order."""
    shown_cards = [
        i
        for i in regime.indicators
        if i.status is IndicatorStatus.ON or i.changed or (card is not None and i.key == card.key)
    ]
    lines = [
        f"The market's weather: {regime.plain_label}. {regime.headline}",
        "Scores:",
        _score(
            "Slow-warning score (macro risk, moves over weeks; the higher of its two parts)",
            regime.scores.macro_risk,
        ),
        _score(
            "Slow-warning score, early part (yield curve inverted for a month within the last "
            "year, Fed hikes, building permits, inflation)",
            regime.scores.macro_early,
        ),
        _score(
            "Slow-warning score, confirming part (credit spreads, jobs, financial conditions, "
            "bank lending)",
            regime.scores.macro_confirming,
        ),
        _score(
            "Market stress score (trend, volatility, breadth, moves daily)",
            regime.scores.market_stress,
        ),
        _score(
            "Fragility (context only: how deep a fall from here could be)", regime.scores.fragility
        ),
    ]
    if shown_cards:
        lines.append("Warning signs that are on or changed:")
    else:
        lines.append("No warning sign is on and none changed in the last 5 sessions.")
    for indicator in shown_cards:
        lines += _signal(indicator, card is not None and indicator.key == card.key)
    links: dict[str, Link] = {}
    for indicator in shown_cards:
        for link in indicator.links:
            links.setdefault(link.url, Link(link.title, link.url))
    return Facts("\n".join(lines), tuple(links.values()), f"As of {regime.session.isoformat()}.")


def system_prompt(facts: Facts) -> str:
    """The task, the facts and the allowed links."""
    allowed = "\n".join(f"- {link.title}: {link.url}" for link in facts.links) or "- none"
    return f"{TASK}\nFACTS\n{facts.as_of}\n{facts.text}\n\nALLOWED LINKS\n{allowed}\n"


def user_prompt(question: str) -> str:
    """The question: ``WHAT_IS_HAPPENING``, or a card's plain name."""
    return question
