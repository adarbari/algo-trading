"""The API's text model, behind screener drafts and regime explanations (ADR 0041, amended
2026-10-08): built once per app from ``config/site/llm.toml`` through the source registry (so
the API imports no vendor module, as ``live.py`` does for quotes). One adapter per
``[[provider]]``, each with its key from ``$ALGOTRADE_LLM_API_KEY_<ID>`` (a file without
``[[provider]]`` is one provider with ``$ALGOTRADE_LLM_API_KEY``), chained by
``FallbackTextModel``: the first provider that answers wins. A remote provider whose key is not
set is left out of the chain with a WARNING (a request to it could only be refused). Off
(``$ALGOTRADE_LLM=off``, the switch of tests, smoke and CI, which wins over every file;
``enabled = false`` or no file): ``None``, and the routes that need it answer 503 with the
reason. A ``llm.toml`` that does not load, or a chain with no usable provider, is the same:
logged at ERROR, the text model off with the message as the reason, and the rest of the API
starts. A ``claude-cli`` provider (the owner's own Claude Code login, run headless) needs no
key and is wired with ``only_users``: the chain skips it for every other user. Every attempt
goes through one ``UsageLedger`` (ADR 0057): priced from ``[[price]]`` (a paid remote provider
without one is a ``ConfigurationError``), recorded in the background to ``usage/llm_calls`` when
the store's ``data_url`` is given, and held to ``[budget]``, its counters seeded from the store
at startup; so even a single provider is wrapped in the chain."""

import logging

from algotrade.config.env import (
    LLM_API_KEY,
    LLM_SWITCH,
    claude_cli_env,
    credential,
    llm_key,
    llm_off,
)
from algotrade.config.site.llm import CLAUDE_CLI, LlmSettings, ProviderSettings
from algotrade.config.site.settings import SiteDocuments, load_llm, load_users
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.text_model.chain import FallbackTextModel
from algotrade.services.text_model.ledger import UsageLedger
from algotrade.services.text_model.model import TextModel
from algotrade.services.text_model.usage import open_recorder, store_seed
from algotrade_sources.framework.registry import build_claude_cli, build_text_model

log = logging.getLogger(__name__)

OFF = "the text model is off: enable it in config/site/llm.toml (ADR 0041)"
FORCED_OFF = f"the text model is forced off by ${LLM_SWITCH}=off (tests, smoke, CI)"


def open_text_model(
    configs: SiteDocuments, data_url: str | None = None
) -> tuple[TextModel | None, str]:
    """-> (the model ``llm.toml`` names with the keys from the environment, why there is none).
    ``None`` when off or when the file is wrong; the reason is what the route answers 503 with.
    ``data_url``: the store the usage is recorded to and the budget counters are seeded from
    (``None``: counted in memory only, as tests do)."""
    if llm_off():  # before anything is read: no file, key or login can turn it on
        return None, FORCED_OFF
    try:
        settings = load_llm(configs)
        if not settings.enabled:
            return None, OFF
        _known_users(settings, configs)
        return _chain(settings, _ledger(settings, data_url)), OFF
    except ConfigurationError as exc:
        log.error("the text model is off, llm.toml is not usable: %s", exc)
        return None, f"the text model is off: {exc}"


def _known_users(settings: LlmSettings, configs: SiteDocuments) -> None:
    """Every ``only_users`` id is a user of ``users.toml``: a typo would silently lock the owner
    out of their own provider."""
    known = {u.user_id for u in load_users(configs).users}
    for provider in settings.providers:
        unknown = sorted(set(provider.only_users) - known)
        if unknown:
            raise ConfigurationError(
                f"llm.toml provider {provider.id} only_users: {unknown} are not in users.toml"
            )


def _ledger(settings: LlmSettings, data_url: str | None) -> UsageLedger:
    if data_url is None:
        return UsageLedger(settings)
    return UsageLedger(settings, open_recorder(data_url), store_seed(data_url))


def _chain(settings: LlmSettings, ledger: UsageLedger) -> TextModel:
    members: list[tuple[str, TextModel]] = []
    for provider in settings.providers:
        if provider.kind == CLAUDE_CLI:
            members.append((provider.id, _claude_cli(provider)))
            continue
        variable = LLM_API_KEY if settings.legacy else llm_key(provider.id)
        key = credential(variable)
        if key is None and not provider.local and not settings.legacy:
            log.warning("text model %s left out: $%s is not set", provider.id, variable)
            continue
        members.append((provider.id, _adapter(provider, key)))
    if not members:
        names = ", ".join(llm_key(p.id) for p in settings.providers)
        raise ConfigurationError(f"no provider has a key: set one of {names}")
    only = {p.id: frozenset(p.only_users) for p in settings.providers if p.only_users}
    only = {pid: users for pid, users in only.items() if pid in dict(members)}
    return FallbackTextModel(members, settings.deadline_s, only_users=only, ledger=ledger)


def _claude_cli(provider: ProviderSettings) -> TextModel:
    return build_claude_cli(
        provider.command,
        provider.model,
        provider.timeout_s,
        provider.retries,
        claude_cli_env(),
        provider.id,
    )


def _adapter(provider: ProviderSettings, key: str | None) -> TextModel:
    return build_text_model(
        provider.base_url,
        provider.model,
        provider.timeout_s,
        provider.answer_limit,
        key,
        provider.retries,
        provider.request,
        provider.id,
    )
