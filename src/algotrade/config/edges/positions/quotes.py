"""``OptionQuotes``: the quote filters of the option selector (design 2.4) from
``config/site/verdict.toml [option_quotes]``: a quote must be two-sided and not crossed, its
spread at most ``max_spread_share`` of the mid, and its volume or open interest at least
``min_volume_or_oi``. Typed apart from ``VerdictSettings``: a filter sets the outcome rows, not the
judge, so it never enters ``settings_hash`` (a tune would re-store every headline for nothing). Read
by the selector once E3a's engine takes it; until then it is parsed and validated only."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table

SECTION = "option_quotes"
KEYS = ("two_sided", "not_crossed", "max_spread_share", "min_volume_or_oi")


@dataclass(frozen=True)
class OptionQuotes:
    two_sided: bool = True
    not_crossed: bool = True
    max_spread_share: float = 0.15
    min_volume_or_oi: int = 1

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "verdict.toml"
    ) -> "OptionQuotes":
        """The ``[option_quotes]`` section, typed; the defaults when the file has none."""
        t = Table(doc, where).table(SECTION, KEYS)
        d = cls()
        return cls(
            two_sided=t.boolean("two_sided", d.two_sided),
            not_crossed=t.boolean("not_crossed", d.not_crossed),
            max_spread_share=t.fraction("max_spread_share", d.max_spread_share),
            min_volume_or_oi=t.integer("min_volume_or_oi", d.min_volume_or_oi, 0),
        )
