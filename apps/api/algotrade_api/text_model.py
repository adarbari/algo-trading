"""The API's text model, behind screener drafts and regime explanations (ADR 0041, amended
2026-10-08): ``algotrade.services.text_model.opening.open_text_model`` called with the source
registry's two builders, so the API imports no vendor module beyond the registry (as ``live.py``
does for quotes). Off, the chain, the ledger and ``only_users``: see that module."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from algotrade.config.site.settings import SiteDocuments
from algotrade.services.text_model.model import TextModel
from algotrade.services.text_model.opening import FORCED_OFF, OFF
from algotrade.services.text_model.opening import open_text_model as _open
from algotrade_sources.framework.registry import build_claude_cli, build_text_model

__all__ = ["FORCED_OFF", "OFF", "open_text_model"]


def open_text_model(
    configs: SiteDocuments,
    data_url: str | None = None,
    *,
    only: Sequence[str] | None = None,
    tee: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[TextModel | None, str]:
    """-> (the model ``llm.toml`` names with the keys from the environment, why there is none)."""
    return _open(configs, data_url, chat=build_text_model, cli=build_claude_cli, only=only, tee=tee)
