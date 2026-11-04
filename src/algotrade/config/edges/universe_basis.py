"""``UniverseBasisLimits``: the thresholds of the run stamp ``universe_basis`` (ADR 0087 decision 6)
from ``config/site/verdict.toml [universe_basis]``: a run's window is ``free`` of survivorship only
when the share of its qualifying listings with no id is at most ``max_no_id_share``, the share of
its delisted names with bars to their last bar is at least ``min_delisted_bars_share``, the share
of those whose delisting return has an unknown basis is at most ``max_unknown_delisting_share``
and the share of stock listings with a null security type is at most ``max_null_type_share``. The
owner may change them. Typed apart from ``VerdictSettings``: they stamp a run, the verdict rule
reads only the stamp, so they never enter ``settings_hash`` or the judge's digest (the loader of
``verdict.py`` only skips the section)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table

SECTION = "universe_basis"
KEYS = (
    "max_no_id_share",
    "min_delisted_bars_share",
    "max_unknown_delisting_share",
    "max_null_type_share",
)


@dataclass(frozen=True)
class UniverseBasisLimits:
    max_no_id_share: float = 0.01
    min_delisted_bars_share: float = 0.98
    max_unknown_delisting_share: float = 0.05
    max_null_type_share: float = 0.05

    @classmethod
    def from_document(
        cls, doc: Mapping[str, Any] | None, where: str = "verdict.toml"
    ) -> "UniverseBasisLimits":
        """The ``[universe_basis]`` section, typed; the defaults when the file has none."""
        t = Table(doc, where).table(SECTION, KEYS)
        d = cls()
        return cls(
            max_no_id_share=t.fraction("max_no_id_share", d.max_no_id_share),
            min_delisted_bars_share=t.fraction(
                "min_delisted_bars_share", d.min_delisted_bars_share
            ),
            max_unknown_delisting_share=t.fraction(
                "max_unknown_delisting_share", d.max_unknown_delisting_share
            ),
            max_null_type_share=t.fraction("max_null_type_share", d.max_null_type_share),
        )
