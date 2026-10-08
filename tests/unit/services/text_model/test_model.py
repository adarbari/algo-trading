"""The text-model seam (ADR 0041, amended): the one adapter satisfies ``TextModel`` for both
callers, and an unavailable model is the one ``core`` error."""

from algotrade.core.model.errors import ModelUnavailableError as CoreError
from algotrade.services.text_model.model import ModelUnavailableError, TextModel
from algotrade_sources.framework.registry import build_text_model


def test_the_adapter_is_a_text_model_with_names() -> None:
    model: TextModel = build_text_model("http://localhost:11434/v1", "llama3.1", 5.0, 100, None)
    assert model.names == ("llama3.1",)


def test_the_seam_re_exports_the_core_error() -> None:
    assert ModelUnavailableError is CoreError
