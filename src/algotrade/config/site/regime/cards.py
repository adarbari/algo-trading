"""The regime indicator cards (``config/site/regime/cards.toml``, ADR 0047;
docs/market-regime-plan.md 5.5): per indicator the plain-language text a non-expert reads
first (``plain_name``, ``one_liner``), what it means (``why_it_matters``,
``what_on_means``), what it did before the big falls (``before``, ``lead_time``,
``false_alarms``), the curated reading list (``links``: the
explanation model may cite only these), ``feature``, the market catalogue field the card
reads its value from (``market.regime_indicators@v1.<key>``, written by the RG3 group), the
display ``range`` of its meter (in the value's stored unit) and ``how`` it is calculated, one
plain sentence whose ``terms`` link to an explainer (returned pre-split, ``terms.py``).

A card whose value comes from one of two sources by session (the S&P 500 trend: SPY's bars, or
the SPX level before they reach back far enough) says which in ``source_by``: the catalogue
field that names the session's source, and per value of it the lineage inputs it means. The
read marks those sources active or not for the session; the card's other inputs are always
active.

``[[source]]`` names the stored inputs that are not macro series (``bars/1d``,
``rates/treasury``, ``universe``): what a card's lineage reaches there is shown as that
source (``services/read/regime/sources.py``; a series is described by ``macro.toml``).

The loader checks shape only: unique keys, features and source inputs, no empty text,
``https`` links, a range with ``min < max``, each term once in ``how``. That a card's
``feature`` is a catalogue field, and that every input its lineage reaches has a source, are
fitness tests."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.config.site.macro import CADENCES
from algotrade.config.site.regime.terms import Term, TextPart, https, split
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
    "range",
    "how",
    "terms",
    "source_by",
)
LINK_KEYS = ("title", "url")
TERM_KEYS = ("text", "url")
RANGE_KEYS = ("min", "max")
SOURCE_KEYS = ("input", "label", "cadence", "url")
SWITCH_KEYS = ("feature", "inputs")


class Documents(Protocol):
    """What the loader needs from a config store (``ConfigStore``)."""

    def load(self, scope: str, kind: str, name: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class CardLink:
    """One reading-list entry: its ``title`` and an ``https`` ``url``."""

    title: str
    url: str


@dataclass(frozen=True)
class CardRange:
    """The meter's display range, in the value's stored unit (``min < max``)."""

    min: float
    max: float


@dataclass(frozen=True)
class InputSource:
    """``[[source]]``: a stored input that is not a macro series (``input``: its table, as a
    feature's lineage names it, e.g. ``bars/1d``), shown as ``label``, updated at ``cadence``;
    ``url``: a page about it (``None``: our own data, nothing public to link)."""

    input: str
    label: str
    cadence: str
    url: str | None = None


@dataclass(frozen=True)
class SourceSwitch:
    """``source_by``: ``feature`` (a catalogue field) names the session's source; ``inputs``:
    per value of it, the lineage inputs (``bars/1d``, ``series:SPX``) that value means."""

    feature: str
    inputs: Mapping[str, tuple[str, ...]]


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
    range: CardRange
    how: tuple[TextPart, ...]
    before: Mapping[str, str] = field(default_factory=dict)
    source_by: SourceSwitch | None = None


@dataclass(frozen=True)
class RegimeCards:
    """``cards.toml``: the cards in file order and the non-series input ``sources`` (none
    without the file)."""

    cards: tuple[RegimeCard, ...] = ()
    sources: tuple[InputSource, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "RegimeCards":
        where = f"{FOLDER}/{NAME}.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("card", "source"))
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
        return cls(cards, _sources(root, where))


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
    return CardLink(_line(t, "title"), https(_line(t, "url"), f"{t.where} url"))


def _tables(t: Table, key: str, what: str) -> list[Table]:
    raw = t.raw(key)
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{t.where} {key}: expected a list of {what}")
    return [Table(e, f"{t.where} {key}[{i}]") for i, e in enumerate(raw)]


def _range(t: Table) -> CardRange:
    raw = t.raw("range")
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{t.where} range: expected a table {{min, max}}")
    sub = Table(raw, f"{t.where} range")
    sub.only(RANGE_KEYS)
    low, high = sub.number("min", None), sub.number("max", None)
    if low is None or high is None or not low < high:
        raise ConfigurationError(f"{sub.where}: expected numbers min < max, got {dict(raw)}")
    return CardRange(low, high)


def _how(t: Table) -> tuple[TextPart, ...]:
    terms = []
    for sub in _tables(t, "terms", "{text, url}"):
        sub.only(TERM_KEYS)
        terms.append(Term(_line(sub, "text"), https(_line(sub, "url"), f"{sub.where} url")))
    return split(_line(t, "how"), tuple(terms), t.where)


def _switch(t: Table) -> SourceSwitch | None:
    raw = t.raw("source_by")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{t.where} source_by: expected a table {{feature, inputs}}")
    sub = Table(raw, f"{t.where} source_by")
    sub.only(SWITCH_KEYS)
    inputs = sub.raw("inputs")
    ok = (
        isinstance(inputs, Mapping)
        and inputs
        and all(
            isinstance(v, list) and v and all(isinstance(i, str) and i for i in v)
            for v in inputs.values()
        )
    )
    if not ok:
        raise ConfigurationError(f"{sub.where} inputs: expected value = [input, ...] per source")
    seen = [i for v in inputs.values() for i in v]
    if len(seen) != len(set(seen)):
        raise ConfigurationError(f"{sub.where} inputs: an input is listed under two values")
    return SourceSwitch(_line(sub, "feature"), {str(k): tuple(v) for k, v in inputs.items()})


def _source(t: Table) -> InputSource:
    t.only(SOURCE_KEYS)
    cadence = _line(t, "cadence")
    if cadence not in CADENCES:
        raise ConfigurationError(f"{t.where} cadence: expected one of {list(CADENCES)}")
    url = https(_line(t, "url"), f"{t.where} url") if t.raw("url") is not None else None
    return InputSource(_line(t, "input"), _line(t, "label"), cadence, url)


def _sources(root: Table, where: str) -> tuple[InputSource, ...]:
    found = tuple(_source(t) for t in _tables(root, "source", "tables ([[source]])"))
    repeated = sorted(k for k, n in Counter(s.input for s in found).items() if n > 1)
    if repeated:
        raise ConfigurationError(f"{where}: source inputs declared more than once: {repeated}")
    return found


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
        range=_range(t),
        how=_how(t),
        before=_before(t),
        source_by=_switch(t),
    )
