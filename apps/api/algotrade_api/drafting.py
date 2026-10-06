"""The API's text model for screener drafts (ADR 0040): built once per app from
``config/site/llm.toml`` and ``$ALGOTRADE_LLM_API_KEY`` through the source registry (so the
API imports no vendor module, as ``live.py`` does for quotes). Off (``enabled = false`` or no
file): ``None``, and the drafting route answers 503 with the reason."""

from algotrade.config.env import LLM_API_KEY, credential
from algotrade.config.site.settings import SiteDocuments, load_llm
from algotrade.services.drafting.model import TextModel
from algotrade_sources.framework.registry import build_text_model

OFF = "natural-language drafts are off: enable them in config/site/llm.toml (ADR 0040)"


def open_drafting(configs: SiteDocuments) -> TextModel | None:
    """The model ``llm.toml`` names, with the key from the environment; ``None`` when off."""
    settings = load_llm(configs)
    if not settings.enabled:
        return None
    return build_text_model(
        settings.base_url,
        settings.model,
        settings.timeout_s,
        settings.answer_limit,
        credential(LLM_API_KEY),
    )
