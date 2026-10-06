"""The cache of regime explanations (ADR 0041, amended 2026-10-06). ``TextCache`` is the
protocol (``get`` / ``put`` a text by key); its backend is ``storage/backends/text_cache.py``
(JSON files under ``var/cache/explanations/``), opened here from the store's URL like the live
recorder's. The key is the session date and the hash of what the answer depends on: which
signals are on and their verdicts, the question and the model's name, so the first click of a
session pays the model and the rest of the team reads the file. What is cached is the model's
raw answer, which is verified again on every read. A derived cache, not data: the API's one
write outside user configs, the live-quote log and screener runs (ADR 0005 exception)."""

import hashlib
import json
from typing import Protocol

from algotrade.services.read.regime.regime import MarketRegime
from algotrade.storage.factory import open_text_cache as open_backend_cache


class TextCache(Protocol):
    def get(self, key: str) -> str | None:
        """The text kept under ``key``, or ``None``."""
        ...

    def put(self, key: str, text: str) -> None:
        """Keep ``text`` under ``key``."""
        ...


def signals_hash(regime: MarketRegime) -> str:
    """A hash of the label and each indicator's verdict and change (not its value: a value
    moving within a verdict does not call the model again; the answer is re-checked anyway)."""
    signals = [[i.key, i.status.value, i.changed] for i in regime.indicators]
    document = json.dumps([regime.label.value, signals], separators=(",", ":"))
    return hashlib.sha256(document.encode()).hexdigest()


def cache_key(regime: MarketRegime, question: str, model_name: str) -> str:
    """``<session date>_<hash of the signals, the question and the model>``."""
    document = json.dumps([signals_hash(regime), question, model_name], separators=(",", ":"))
    digest = hashlib.sha256(document.encode()).hexdigest()[:32]
    return f"{regime.session.isoformat()}_{digest}"


def open_text_cache(data_url: str) -> TextCache:
    """The cache beside the store at ``data_url`` (the API's)."""
    return open_backend_cache(data_url)
