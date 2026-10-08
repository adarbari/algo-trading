"""Site settings for natural-language screener drafts (ADR 0041): the text model
(``config/site/llm.toml``: the chain of OpenAI-compatible endpoints and models that answer, how
long a request may take; off by default, the key only from the environment, ``config/env.py``)
and the phrasebook (``config/site/phrasebook.toml``: trader vocabulary mapped to catalogue
fields with a hint on thresholds, listed in the prompt after the catalogue)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

KEYS = (
    "enabled",
    "base_url",
    "model",
    "timeout_s",
    "answer_limit",
    "retries",
    "request",
    "deadline_s",
    "provider",
    "price",
    "budget",
)
PRICE_KEYS = ("model", "input_per_mtok", "output_per_mtok", "free")
BUDGET_KEYS = ("daily_usd", "monthly_usd", "over")
OVER = ("free", "refuse")
PRICED, REPORTED, FREE = "price", "reported", "free"  # a rate's basis (usage/llm_calls cost_basis)
PROVIDER_KEYS = (
    "id",
    "kind",
    "base_url",
    "model",
    "timeout_s",
    "answer_limit",
    "retries",
    "request",
    "command",
    "only_users",
)
KINDS = ("openai", "claude-cli")
CLAUDE_CLI = "claude-cli"
RESERVED_REQUEST_KEYS = ("model", "messages", "temperature", "max_tokens", "response_format")
LOOPBACK = ("localhost", "127.0.0.1", "::1")
PHRASE_KEYS = ("say", "fields", "hint")
LEGACY_ID = "default"  # the one provider of a file without [[provider]]
_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")


@dataclass(frozen=True)
class ProviderSettings:
    """One text-model provider: ``id`` (lower-case letters, digits and ``_``; names its key
    ``ALGOTRADE_LLM_API_KEY_<ID upper>``, ``config/env.py``), ``base_url`` its OpenAI-compatible
    root (the one with ``/chat/completions`` under it: Gemini, Groq, OpenRouter, Ollama,
    Anthropic's compatibility endpoint), ``model`` its model id, ``timeout_s`` the longest one
    request may take, ``answer_limit`` the longest answer asked for, in tokens (a draft is a
    few hundred, but a model that thinks first, Gemini 3.x, spends thinking tokens from the same
    budget: ~2,000), ``retries`` how many times a busy provider (429, 5xx) or a dropped
    connection is retried before the chain moves on (0: never), ``request`` extra fields sent
    with every request as given (``reasoning_effort = "low"`` tells Gemini to think briefly):
    strings, numbers and booleans only, never the ones the adapter sets. ``only_users``: the
    registry users it answers (empty: everyone; any kind may set it). ``kind = "claude-cli"``
    runs Claude Code headless on this machine under the owner's own login instead of calling an
    endpoint: it has ``command`` (the absolute path of ``claude``; no ``base_url``), ``model``
    ("haiku", "sonnet"), ``timeout_s`` and ``retries`` (default 0), and must set ``only_users``:
    a subscription login never answers anyone else (ADR 0041, amended 2026-10-08)."""

    id: str
    base_url: str
    model: str
    timeout_s: float = 60.0
    answer_limit: int = 8000
    retries: int = 2
    request: Mapping[str, str | float | bool] = field(default_factory=lambda: MappingProxyType({}))
    kind: str = "openai"
    command: str = ""
    only_users: tuple[str, ...] = ()

    @property
    def worst_case_s(self) -> float:
        """The longest this provider can keep a chain waiting: every attempt timing out, plus
        the pauses between them (a bare 429 waits 20 s; a ``Retry-After`` may wait longer)."""
        if self.kind == CLAUDE_CLI:
            return self.timeout_s * (self.retries + 1)
        pauses: float = sum(max(20.0, 3.0 * 2.0**a) for a in range(self.retries))
        return self.timeout_s * (self.retries + 1) + pauses

    @property
    def local(self) -> bool:
        """Served from this machine: needs no key."""
        return self.kind == CLAUDE_CLI or urlsplit(self.base_url).hostname in LOOPBACK


@dataclass(frozen=True)
class Rate:
    """What a provider's calls cost (ADR 0057): ``basis`` ``price`` (per million tokens, the
    ``[[price]]`` of its model), ``reported`` (a subscription login, ``claude-cli``: the notional
    cost Claude Code reports) or ``free`` (a local server, or a model declared ``free = true``)."""

    basis: str
    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0

    @property
    def spends(self) -> bool:
        """Counts against the budget: everything but a free provider."""
        return self.basis != FREE


@dataclass(frozen=True)
class PriceSettings:
    """One ``[[price]]``: a model's price in USD per million input and output tokens, or
    ``free = true`` (a free tier). A paid remote model without one is a ``ConfigurationError``:
    missing data never counts as $0."""

    model: str
    input_per_mtok: float = 0.0
    output_per_mtok: float = 0.0
    free: bool = False


@dataclass(frozen=True)
class BudgetSettings:
    """``[budget]``: ``daily_usd`` / ``monthly_usd`` (exchange-calendar day and month; ``None``:
    no cap) and ``over``: what a spent budget does: ``free`` (only the free providers answer,
    the priced and reported ones are skipped) or ``refuse`` (every call is refused)."""

    daily_usd: float | None = None
    monthly_usd: float | None = None
    over: str = "free"


@dataclass(frozen=True)
class LlmSettings:
    """``llm.toml``: the text model behind screener drafts and regime explanations (ADR 0041,
    amended 2026-10-08). ``providers`` is the chain in the order tried: the ``[[provider]]``
    tables, whose ``timeout_s``, ``answer_limit``, ``retries`` and ``request`` fall back to the
    file's top-level values; a file without them is one provider from the top-level
    ``base_url`` and ``model`` (``legacy``: its key is ``$ALGOTRADE_LLM_API_KEY``). Both forms
    in one file is a ``ConfigurationError``. ``deadline_s``: once a chain has spent this long, it
    starts no further provider. Read-only."""

    enabled: bool = False
    providers: tuple[ProviderSettings, ...] = (
        # Ollama's default: nothing leaves the machine
        ProviderSettings(LEGACY_ID, "http://localhost:11434/v1", "llama3.1"),
    )
    deadline_s: float = 120.0
    legacy: bool = True
    prices: tuple[PriceSettings, ...] = ()
    budget: BudgetSettings = field(default_factory=BudgetSettings)

    def rate(self, provider: ProviderSettings) -> Rate:
        """What ``provider``'s calls cost: ``reported`` for ``claude-cli``, ``free`` for a local
        server, else its model's ``[[price]]``; no price is a ``ConfigurationError``."""
        if provider.kind == CLAUDE_CLI:
            return Rate(REPORTED)
        price = next((p for p in self.prices if p.model == provider.model), None)
        if price is None:
            if provider.local:
                return Rate(FREE)
            raise ConfigurationError(
                f"llm.toml provider {provider.id}: no [[price]] for model {provider.model!r}; "
                "add its price per million tokens, or `free = true` for a free tier (a missing "
                "price must not count as $0, ADR 0057)"
            )
        if price.free:
            return Rate(FREE)
        return Rate(PRICED, price.input_per_mtok, price.output_per_mtok)

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "LlmSettings":
        where = "llm.toml"
        reject_secrets(doc or {}, where)
        t = Table(doc, where)
        t.only(KEYS)
        d = cls()
        shared = ProviderSettings(
            LEGACY_ID,
            "",
            "",
            timeout_s=t.number("timeout_s", 60.0, 1),
            answer_limit=t.integer("answer_limit", 8000, 1),
            retries=t.integer("retries", 2, 0),
            request=_request(t),
        )
        raw = t.raw("provider")
        if raw is None:
            legacy = ProviderSettings(
                LEGACY_ID,
                _endpoint(t.text("base_url", d.providers[0].base_url), f"{where} base_url"),
                t.text("model", d.providers[0].model),
                shared.timeout_s,
                shared.answer_limit,
                shared.retries,
                shared.request,
            )
            providers: tuple[ProviderSettings, ...] = (legacy,)
            is_legacy = True
        else:
            clash = [k for k in ("base_url", "model") if k in t.names()]
            if clash:
                raise ConfigurationError(
                    f"{where}: {clash} at the top level and [[provider]] tables: use one form "
                    "(each provider names its own base_url and model)"
                )
            providers, is_legacy = _providers(raw, shared, where), False
        # The deadline must leave every provider but the last its whole worst case, or a
        # hanging primary would use up the time and the fallback never gets its turn. Unset: the
        # sum of every provider's worst case (the chain is then bounded, never cut short).
        needed = sum(p.worst_case_s for p in providers[:-1])
        total = needed + providers[-1].worst_case_s
        deadline = t.number("deadline_s", total, 1)
        if deadline <= needed:
            raise ConfigurationError(
                f"{where} deadline_s: {deadline:g} s is shorter than the providers before the "
                f"last can take ({needed:g} s: timeout_s x (retries + 1) plus the pauses); "
                "raise it, or lower their timeout_s / retries, so the fallback is reached"
            )
        settings = cls(
            enabled=t.boolean("enabled", d.enabled),
            providers=providers,
            deadline_s=deadline,
            legacy=is_legacy,
            prices=_prices(t.raw("price"), where),
            budget=_budget(t.table("budget", BUDGET_KEYS)),
        )
        if settings.enabled:
            for provider in providers:
                settings.rate(provider)
        return settings


def _prices(raw: Any, where: str) -> tuple[PriceSettings, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{where} price: expected a list of tables ([[price]])")
    out: list[PriceSettings] = []
    for i, entry in enumerate(raw):
        t = Table(entry, f"{where} [[price]][{i}]")
        t.only(PRICE_KEYS)
        model = t.text("model", "")
        if not model:
            raise ConfigurationError(f"{t.where}: model is required")
        if any(p.model == model for p in out):
            raise ConfigurationError(f"{t.where} model: {model!r} is priced twice")
        if t.boolean("free", False):
            if "input_per_mtok" in t.names() or "output_per_mtok" in t.names():
                raise ConfigurationError(f"{t.where}: a free model has no price")
            out.append(PriceSettings(model, free=True))
            continue
        if "input_per_mtok" not in t.names() or "output_per_mtok" not in t.names():
            raise ConfigurationError(
                f"{t.where}: input_per_mtok and output_per_mtok (USD per million tokens), "
                "or free = true"
            )
        out.append(
            PriceSettings(
                model, t.number("input_per_mtok", 0.0, 0.0), t.number("output_per_mtok", 0.0, 0.0)
            )
        )
    return tuple(out)


def _budget(t: Table) -> BudgetSettings:
    over = t.text("over", "free")
    if over not in OVER:
        raise ConfigurationError(f"{t.where} over: expected one of {list(OVER)}, got {over!r}")
    daily, monthly = t.number("daily_usd", None, 0.0), t.number("monthly_usd", None, 0.0)
    if daily is not None and monthly is not None and daily > monthly:
        raise ConfigurationError(f"{t.where}: daily_usd {daily:g} is above monthly_usd {monthly:g}")
    return BudgetSettings(daily, monthly, over)


def _providers(raw: Any, shared: ProviderSettings, where: str) -> tuple[ProviderSettings, ...]:
    if not isinstance(raw, list) or not raw or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{where} provider: expected a list of tables ([[provider]])")
    out: list[ProviderSettings] = []
    for i, entry in enumerate(raw):
        t = Table(entry, f"{where} [[provider]][{i}]")
        t.only(PROVIDER_KEYS)
        pid = t.text("id", "")
        if not _ID.fullmatch(pid):
            raise ConfigurationError(
                f"{t.where} id: expected lower-case letters, digits and _ (starting with a "
                f"letter), got {pid!r}"
            )
        if any(p.id == pid for p in out):
            raise ConfigurationError(f"{t.where} id: {pid!r} is used twice")
        kind = t.text("kind", "openai")
        if kind not in KINDS:
            raise ConfigurationError(f"{t.where} kind: expected one of {list(KINDS)}, got {kind!r}")
        only = _only_users(t)
        if kind == CLAUDE_CLI:
            out.append(_claude_cli(t, pid, only, shared))
            continue
        if "command" in t.names():
            raise ConfigurationError(f"{t.where}: command belongs to kind = {CLAUDE_CLI!r}")
        if "base_url" not in t.names() or "model" not in t.names():
            raise ConfigurationError(f"{t.where}: base_url and model are required")
        out.append(
            ProviderSettings(
                pid,
                _endpoint(t.text("base_url", ""), f"{t.where} base_url"),
                t.text("model", ""),
                t.number("timeout_s", shared.timeout_s, 1),
                t.integer("answer_limit", shared.answer_limit, 1),
                t.integer("retries", shared.retries, 0),
                _request(t) if "request" in t.names() else shared.request,
                only_users=only,
            )
        )
    return tuple(out)


def _only_users(t: Table) -> tuple[str, ...]:
    users = t.strings("only_users", ())
    if "only_users" in t.names() and (not users or not all(u.strip() for u in users)):
        raise ConfigurationError(f"{t.where} only_users: expected one or more user ids")
    return tuple(u.strip() for u in users)


def _claude_cli(
    t: Table, pid: str, only: tuple[str, ...], shared: ProviderSettings
) -> ProviderSettings:
    """A Claude Code provider: the owner's own login, so only the users it names are answered
    (its own ``retries`` default is 0: a refused login or a used-up limit is not retried)."""
    if not only:
        raise ConfigurationError(
            f"{t.where}: kind = {CLAUDE_CLI!r} needs only_users (a subscription login must "
            "not answer other users; name the owner)"
        )
    stray = [k for k in ("base_url", "answer_limit", "request") if k in t.names()]
    if stray:
        raise ConfigurationError(f"{t.where}: {stray} do not apply to kind = {CLAUDE_CLI!r}")
    command = t.text("command", "")
    if not command.startswith("/"):
        raise ConfigurationError(
            f"{t.where} command: expected the absolute path of claude (launchd's PATH is "
            f"minimal), got {command!r}"
        )
    if "model" not in t.names():
        raise ConfigurationError(f'{t.where}: model is required ("haiku", "sonnet")')
    return ProviderSettings(
        pid,
        "",
        t.text("model", ""),
        t.number("timeout_s", shared.timeout_s, 1),
        shared.answer_limit,
        t.integer("retries", 0, 0),
        kind=CLAUDE_CLI,
        command=command,
        only_users=only,
    )


def _request(t: Table) -> Mapping[str, str | float | bool]:
    raw = t.raw("request")
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{t.where} request: expected a table ([request])")
    reserved = sorted(set(raw) & set(RESERVED_REQUEST_KEYS))
    if reserved:
        raise ConfigurationError(f"{t.where} [request]: the adapter sets {reserved}; remove them")
    for key, value in raw.items():
        if not isinstance(value, str | int | float | bool):
            raise ConfigurationError(
                f"{t.where} [request] {key}: expected a string, number or boolean, got {value!r}"
            )
    return MappingProxyType(dict(raw))


def _endpoint(url: str, where: str) -> str:
    """An ``http(s)`` URL; plain ``http`` only to this machine, so the key never travels in
    clear (the sentence and the catalogue neither)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigurationError(f"{where}: expected an http(s) URL, got {url!r}")
    if parts.scheme == "http" and parts.hostname not in LOOPBACK:
        raise ConfigurationError(f"{where}: a remote endpoint must use https, got {url!r}")
    return url.rstrip("/")


@dataclass(frozen=True)
class Phrase:
    """One phrasebook entry: what the trader ``say``s (any of the words), the catalogue
    ``fields`` that express it (exact names) and a ``hint`` on how to use them (the gate, a
    confirmation or a score, typical thresholds, what not to combine)."""

    say: tuple[str, ...]
    fields: tuple[str, ...]
    hint: str = ""


@dataclass(frozen=True)
class PhrasebookSettings:
    """``phrasebook.toml``: the phrases in file order (none without the file)."""

    phrases: tuple[Phrase, ...] = ()

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "PhrasebookSettings":
        where = "phrasebook.toml"
        reject_secrets(doc or {}, where)
        root = Table(doc, where)
        root.only(("phrase",))
        raw = root.raw("phrase") or []
        if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
            raise ConfigurationError(f"{where} phrase: expected a list of tables ([[phrase]])")
        return cls(tuple(_phrase(Table(e, f"{where} [[phrase]][{i}]")) for i, e in enumerate(raw)))


def _phrase(t: Table) -> Phrase:
    t.only(PHRASE_KEYS)
    say, fields = t.strings("say", ()), t.strings("fields", ())
    if not say or not all(s.strip() for s in say):
        raise ConfigurationError(f"{t.where} say: expected one or more non-empty strings")
    if not fields or not all(f.strip() for f in fields):
        raise ConfigurationError(f"{t.where} fields: expected one or more catalogue field names")
    return Phrase(tuple(s.strip() for s in say), tuple(fields), t.text("hint", "").strip())
