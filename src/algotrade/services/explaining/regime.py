"""``explain_regime``: the use case behind ``POST /regime/explain`` (ADR 0041, amended
2026-10-06). Loads the regime of the request's session, answers the one fixed question ("what
is happening?") or a card's question (its plain name) from the cache when the same signals
were explained before, else from the text model (counted against the user's rate limit; a
cache hit is free), and keeps an answer in the cache only when it checked out. Nothing is
asked of the model unless the caller asks; an UNKNOWN regime has nothing to explain. The
question is never free text from the page: it is one of the fixed ones or a card's name."""

from dataclasses import dataclass

from algotrade.core.model.completion import CallTag
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.explaining.answer import Explanation, ask, verify
from algotrade.services.explaining.cache import TextCache, cache_key
from algotrade.services.explaining.limits import RateLimiter
from algotrade.services.explaining.prompt import WHAT_IS_HAPPENING, regime_facts
from algotrade.services.read.context import NotFoundError, ReadContext
from algotrade.services.read.regime.regime import RegimeLabel, load_regime
from algotrade.services.text_model.model import TextModel


@dataclass(frozen=True)
class Explained:
    """The explanation and whether it came from the cache."""

    explanation: Explanation
    cached: bool


def explain_regime(
    ctx: ReadContext,
    model: TextModel,
    cache: TextCache,
    limiter: RateLimiter,
    user: str,
    question: str | None,
    card: str | None,
) -> Explained:
    """The regime of ``ctx.session`` in plain words: ``question`` (only "what is happening?")
    or ``card`` (a card key of the regime). ``ConfigurationError`` for neither or both, another
    question or an UNKNOWN regime; ``NotFoundError`` for a card the regime does not have;
    ``RateLimitedError`` when ``user`` called the model too often; ``ModelUnavailableError``."""
    if (question is None) == (card is None):
        raise ConfigurationError("ask one of question or card")
    if question is not None and " ".join(question.lower().split()) != WHAT_IS_HAPPENING:
        raise ConfigurationError(f"the only question is {WHAT_IS_HAPPENING!r}; or name a card")
    regime = load_regime(ctx)
    if regime.label is RegimeLabel.UNKNOWN:
        raise ConfigurationError("the regime is not computed for this session: nothing to explain")
    chosen = None
    if card is not None:
        chosen = next((i for i in regime.indicators if i.key == card), None)
        if chosen is None:
            raise NotFoundError(f"the regime has no card {card!r}")
    asked = WHAT_IS_HAPPENING if chosen is None else chosen.plain_name
    facts = regime_facts(regime, chosen)
    # An answer is kept under the model that gave it (``Completion.model``), and looked up under
    # each model the chain may answer this user as, in order: a fallback's answer is never the
    # primary's, and a provider limited to some users (the owner's Claude login) never has its
    # answer served to anyone else.
    for name in model.names_for(user):
        kept = cache.get(cache_key(regime, asked, name))
        if kept is not None:
            explanation = verify(kept, facts)
            if explanation.checked:
                return Explained(explanation, True)
    limiter.take(user, "regime explanations")
    answer = ask(model, facts, asked, CallTag("regime-explain", user))
    explanation = verify(answer.text, facts)
    if explanation.checked:
        cache.put(cache_key(regime, asked, answer.model), answer.text)
    return Explained(explanation, False)
