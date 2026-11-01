"""``ExitRuleSettings``: the published historical exit rule's parameters (ADR 0083 decision 3, ADR
0088) from ``config/site/verdict.toml [exit_rule]``: the fewest winning trades its percentile
rests on, the percentile of their adverse moves that is the stop, and the ATR multiple of the
share fallback. Typed apart from ``VerdictSettings``: it is a reading of the evidence, not a judge
input, so it never enters ``settings_hash`` or a fingerprint (the loader of ``verdict.py`` only
skips the section)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table
from algotrade.core.model.errors import ConfigurationError

SECTION = "exit_rule"
KEYS = ("min_winners", "stop_percentile", "atr_multiple")


@dataclass(frozen=True)
class ExitRuleSettings:
    min_winners: int
    stop_percentile: float = 0.80
    atr_multiple: float = 2.0

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "verdict.toml"
    ) -> "ExitRuleSettings | None":
        """The ``[exit_rule]`` section, typed; None when the file has none (E12a appends it, and
        ``min_winners`` has no default: the implementing PR chooses it)."""
        if not doc or SECTION not in doc:
            return None
        t = Table(doc, where).table(SECTION, KEYS)
        if "min_winners" not in t.names():
            raise ConfigurationError(f"{t.where} min_winners: required")
        return cls(
            min_winners=t.integer("min_winners", 0, 1),
            stop_percentile=t.fraction("stop_percentile", 0.80),
            atr_multiple=t.number("atr_multiple", 2.0, 0.1),
        )
