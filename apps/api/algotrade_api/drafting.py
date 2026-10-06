"""The API's text model for screener drafts (ADR 0041): built once per app from
``config/site/llm.toml`` and ``$ALGOTRADE_LLM_API_KEY`` through the source registry (so the
API imports no vendor module, as ``live.py`` does for quotes). Off (``enabled = false`` or no
file): ``None``, and the drafting route answers 503 with the reason. A ``llm.toml`` that does not
load is the same: logged at ERROR, drafting off with the file's message as the reason, and the
rest of the API starts."""

import logging

from algotrade.config.env import LLM_API_KEY, credential
from algotrade.config.site.settings import SiteDocuments, load_llm
from algotrade.core.model.errors import ConfigurationError
from algotrade.services.drafting.model import TextModel
from algotrade_sources.framework.registry import build_text_model

log = logging.getLogger(__name__)

OFF = "natural-language drafts are off: enable them in config/site/llm.toml (ADR 0041)"


def open_drafting(configs: SiteDocuments) -> tuple[TextModel | None, str]:
    """-> (the model ``llm.toml`` names with the key from the environment, why there is none).
    ``None`` when off or when the file is wrong; the reason is what the route answers 503 with."""
    try:
        settings = load_llm(configs)
    except ConfigurationError as exc:
        log.error("natural-language drafts are off, llm.toml is not usable: %s", exc)
        return None, f"natural-language drafts are off: {exc}"
    if not settings.enabled:
        return None, OFF
    model = build_text_model(
        settings.base_url,
        settings.model,
        settings.timeout_s,
        settings.answer_limit,
        credential(LLM_API_KEY),
        settings.retries,
        settings.request,
    )
    return model, OFF
