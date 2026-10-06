"""The regime indicator cards (``config/site/regime/cards.toml``, ADR 0047;
docs/market-regime-plan.md 5.5): per indicator the plain-language text a non-expert reads
first (``plain_name``, ``one_liner``), what it means (``why_it_matters``,
``what_on_means``), what it did before the big falls (``before``, ``lead_time``,
``false_alarms``), the curated reading list (``links``: the
explanation model may cite only these) and ``feature``, the market catalogue field the card
reads its value from (``market.regime_indicators@v1.<key>``, written by the RG3 group).

The loader checks shape only: unique keys and features, no empty text, ``https`` links. That a
card's ``feature`` is a catalogue field is a fitness test once the group exists."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FOLDER = "regime"
NAME = "cards"
PACES = ("slow", "fast")
KEYS = (
    "key",
    "technical_name",
    "pace",
    "feature",
    "plain_name",
    "one_liner",
    "why_it_matters",
    "what_on_means",
    "lead_time",
    "false_alarms",
    "links",
    "before",
)
LINK_KEYS = ("title", "url")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class CardLink:
    """One reading-list entry: its ``title`` and an ``https`` ``url``."""

    title: str
    url: str


@dataclass(frozen=True)
class RegimeCard:
    """One indicator's card. ``before``: episode label (``"2008"``) -> one line, in file order;
    ``pace``: ``slow`` (macro) or ``fast`` (market); ``feature``: the catalogue field of its
    value (its on / off verdict and 5-session change are the same name plus ``_on`` /
    ``_changed``, read by ``services.read.regime``)."""

    key: str
    technical_name: str
    pace: str
    feature: str
    plain_name: str
    one_liner: str
    why_it_matters: str
    what_on_means: str
    lead_time: str
    false_alarms: str
    links: tuple[CardLink, ...]
    before: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeCards:
    """``cards.toml``: the cards in file order (none without the file)."""

    cards: tuple[RegimeCard, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "RegimeCards":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("card",))
        raw = root.raw("card") or []
        if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
            raise ConfigurationError(f"{where} card: expected a list of tables ([[card]])")
        cards = tuple(_card(Table(e, f"{where} [[card]][{i}]")) for i, e in enumerate(raw))
        for what in ("key", "feature"):
            repeated = sorted(
                k for k, n in Counter(getattr(c, what) for c in cards).items() if n > 1
            )
            if repeated:
                raise ConfigurationError(f"{where}: {what}s declared more than once: {repeated}")
        return cls(cards)


def load_cards(configs: Documents) -> RegimeCards:
    """``config/site/regime/cards.toml``; missing: no cards."""
    return RegimeCards.from_document(configs.load("site", FOLDER, NAME))


def _line(t: Table, key: str) -> str:
    if t.raw(key) is None:
        raise ConfigurationError(f"{t.where} {key}: required")
    value = " ".join(t.text(key, "").split())
    if not value:
        raise ConfigurationError(f"{t.where} {key}: expected a non-empty string")
    return value


def _link(t: Table) -> CardLink:
    t.only(LINK_KEYS)
    url = _line(t, "url")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ConfigurationError(f"{t.where} url: expected an https URL, got {url!r}")
    return CardLink(_line(t, "title"), url)


def _links(t: Table) -> tuple[CardLink, ...]:
    raw = t.raw("links")
    if not isinstance(raw, list) or not raw or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{t.where} links: expected a non-empty list of {{title, url}}")
    return tuple(_link(Table(e, f"{t.where} links[{i}]")) for i, e in enumerate(raw))


def _before(t: Table) -> dict[str, str]:
    raw = t.raw("before")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{t.where} before: expected a table of episode = line")
    sub = Table(raw, f"{t.where} [before]")
    return {name: _line(sub, name) for name in sub.names()}


def _card(t: Table) -> RegimeCard:
    t.only(KEYS)
    pace = _line(t, "pace")
    if pace not in PACES:
        raise ConfigurationError(f"{t.where} pace: expected one of {list(PACES)}, got {pace!r}")
    return RegimeCard(
        key=_line(t, "key"),
        technical_name=_line(t, "technical_name"),
        pace=pace,
        feature=_line(t, "feature"),
        plain_name=_line(t, "plain_name"),
        one_liner=_line(t, "one_liner"),
        why_it_matters=_line(t, "why_it_matters"),
        what_on_means=_line(t, "what_on_means"),
        lead_time=_line(t, "lead_time"),
        false_alarms=_line(t, "false_alarms"),
        links=_links(t),
        before=_before(t),
    )
