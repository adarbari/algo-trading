"""Site settings for natural-language screener drafts (ADR 0041): the text model
(``config/site/llm.toml``: which OpenAI-compatible endpoint and model answer, how long a request
may take; off by default, the key only from the environment, ``config/env.py``) and the
phrasebook (``config/site/phrasebook.toml``: trader vocabulary mapped to catalogue fields with a
hint on thresholds, listed in the prompt after the catalogue)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

KEYS = ("enabled", "base_url", "model", "timeout_s", "answer_limit")
LOOPBACK = ("localhost", "127.0.0.1", "::1")
PHRASE_KEYS = ("say", "fields", "hint")


@dataclass(frozen=True)
class LlmSettings:
    """``llm.toml``: ``base_url`` is the provider's OpenAI-compatible root (the one with
    ``/chat/completions`` under it: Gemini, Groq, OpenRouter, Ollama, Anthropic's compatibility
    endpoint); ``model`` its model id; ``timeout_s`` the longest one request may take;
    ``answer_limit`` the longest answer asked for, in tokens (a draft is a few hundred)."""

    enabled: bool = False
    base_url: str = "http://localhost:11434/v1"  # Ollama's default: nothing leaves the machine
    model: str = "llama3.1"
    timeout_s: float = 60.0
    answer_limit: int = 2000

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "LlmSettings":
        where = "llm.toml"
        reject_secrets(doc or {}, where)
        t = Table(doc, where)
        t.only(KEYS)
        d = cls()
        return cls(
            enabled=t.boolean("enabled", d.enabled),
            base_url=_endpoint(t.text("base_url", d.base_url), f"{where} base_url"),
            model=t.text("model", d.model),
            timeout_s=t.number("timeout_s", d.timeout_s, 1),
            answer_limit=t.integer("answer_limit", d.answer_limit, 1),
        )


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
