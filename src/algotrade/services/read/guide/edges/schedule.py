"""An edge's schedule and holding period in plain words (ADR 0051): what sets a trade off
(``trigger``: the document's ``schedule``) and how long it is held (``holding``: its outcome's
``horizon_sessions``), each with the glossary term that explains it (``trigger_term``). Pure
functions over the typed edge document; no store, no session."""

from collections.abc import Container

from algotrade.config.edges.document import event_class, event_subtype
from algotrade.config.edges.schedules.markets import market_trigger
from algotrade.core.time.windows import window_name

SHORT_SESSIONS = 5  # holding up to this many sessions: "short"; up to MEDIUM_SESSIONS: "medium"
MEDIUM_SESSIONS = 21
BANDS = ("short", "medium", "long")  # the holding bands of the Guide's filter, shortest first

CALENDAR_WORDS = {
    "turn_of_month": "Around the turn of the month",
    "opex_week": "In option-expiration week",
    "after_monthly_expiry": "On the first session after a monthly option expiry",
    "quarter_end": "Around each quarter end",
    "pre_month_end": "In the last sessions before a month end",
    "year_turn": "Around the turn of the year",
    "pre_holiday": "Before a market holiday",
}
EVENT_WORDS = {
    "earnings_reaction": "After a company reports earnings",
    "earnings_reaction_session": "On the day a company's earnings report moves the price",
    "earnings_expected": "Ahead of an expected earnings report",
    "index_change": "When the S&P 500 changes a member",
    "filing_8k": "When a company files an 8-K",
    "nt_late_filing": "When a company files a late-filing notice",
    "tender_offer": "When a tender offer is filed",
    "earnings_date_shift": "When a company moves its earnings date",
}
SUBTYPE_WORDS = {
    "addition": "a name joins",
    "deletion": "a name leaves",
    "later": "to a later date",
    "earlier": "to an earlier date",
}
MARKET_WORDS = {"vix_spike": "When the VIX spikes"}


def trigger_text(schedule: str) -> str:
    """What sets a trade off, in words: ``every_session`` -> ``Every trading day``."""
    window = window_name(schedule)
    if window is not None:
        return CALENDAR_WORDS.get(window, window.replace("_", " ").capitalize())
    market = market_trigger(schedule)
    if market is not None:
        return MARKET_WORDS.get(market, market.replace("_", " ").capitalize())
    event = event_class(schedule)
    if event is not None:
        head = EVENT_WORDS.get(event, event.replace("_", " ").capitalize())
        sub = event_subtype(schedule)
        if sub is None:
            return head
        return f"{head} ({SUBTYPE_WORDS.get(sub) or _subtype(event, sub)})"
    return {
        "every_session": "Every trading day",
        "month_end": "Once a month, at the month end",
    }.get(schedule, schedule.replace("_", " ").capitalize())


def _subtype(event: str, sub: str) -> str:
    return f"Item {sub}" if event == "filing_8k" else sub


def trigger_term(schedule: str, terms: Container[str]) -> str | None:
    """The glossary term id that explains ``schedule`` (``None``: none written)."""
    window = window_name(schedule)
    market = market_trigger(schedule)
    event = event_class(schedule)
    if window is not None:
        candidates = [f"calendar_{window}"]
    elif market is not None:
        candidates = [f"market_trigger_{market}", "schedule_on_market"]
    elif event is not None:
        sub = event_subtype(schedule)
        candidates = ([f"event_class_{event}_{sub.replace('.', '_')}"] if sub else []) + [
            f"event_class_{event}"
        ]
    else:
        return None
    return next((c for c in candidates if c in terms), None)


def holding_text(horizons: tuple[int, ...]) -> str:
    """The holding period in words: ``5 sessions``, ``5 or 21 sessions``."""
    shown = [str(h) for h in horizons]
    head = shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " or " + shown[-1]
    return f"{head} session" + ("" if horizons == (1,) else "s")


def holding_band(horizons: tuple[int, ...]) -> str:
    """The band (``BANDS``) of the longest horizon: up to 5 sessions short, up to 21 medium."""
    longest = max(horizons)
    if longest <= SHORT_SESSIONS:
        return BANDS[0]
    return BANDS[1] if longest <= MEDIUM_SESSIONS else BANDS[2]
