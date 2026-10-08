"""The API's text model, behind screener drafts and regime explanations (ADR 0041, amended
2026-10-08): built once per app from ``config/site/llm.toml`` through the source registry (so
the API imports no vendor module, as ``live.py`` does for quotes). One adapter per
``[[provider]]``, each with its key from ``$ALGOTRADE_LLM_API_KEY_<ID>`` (a file without
``[[provider]]`` is one provider with ``$ALGOTRADE_LLM_API_KEY``), chained by
``FallbackTextModel``: the first provider that answers wins. A remote provider whose key is not
set is left out of the chain with a WARNING (a request to it could only be refused). Off
(``enabled = false`` or no file): ``None``, and the routes that need it answer 503 with the
reason. A ``llm.toml`` that does not load, or a chain with no usable provider, is the same:
logged at ERROR, the text model off with the message as the reason, and the rest of the API
starts. A ``claude-cli`` provider (the owner's own Claude Code login, run headless) needs no
key and is wired with ``only_users``: the chain skips it for every other user."""

import logging

from algotrade.config.env import LLM_API_KEY, claude_cli_env, credential, llm_key
from algotrade.config.site.llm import CLAUDE_CLI, LlmSettings, ProviderSettings
from algotrade.config.site.settings import SiteDocuments, load_llm
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.text_model.chain import FallbackTextModel
from algotrade.services.text_model.model import TextModel
from algotrade_sources.framework.registry import build_claude_cli, build_text_model

log = logging.getLogger(__name__)

OFF = "the text model is off: enable it in config/site/llm.toml (ADR 0041)"


def open_text_model(configs: SiteDocuments) -> tuple[TextModel | None, str]:
    """-> (the model ``llm.toml`` names with the keys from the environment, why there is none).
    ``None`` when off or when the file is wrong; the reason is what the route answers 503 with."""
    try:
        settings = load_llm(configs)
        if not settings.enabled:
            return None, OFF
        return _chain(settings), OFF
    except ConfigurationError as exc:
        log.error("the text model is off, llm.toml is not usable: %s", exc)
        return None, f"the text model is off: {exc}"


def _chain(settings: LlmSettings) -> TextModel:
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
    if len(members) == 1 and not only:
        return members[0][1]
    return FallbackTextModel(members, settings.deadline_s, only_users=only)


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
