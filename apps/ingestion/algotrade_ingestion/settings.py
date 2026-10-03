"""Typed view of ``config/site/sources.toml`` (L3). Missing file or keys fall back to defaults."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.storage.config_store import ConfigStore


@dataclass(frozen=True)
class SourcesSettings:
    raw_retention_days: int = 90
    cboe_enabled: bool = True
    cboe_workers: int = 4
    universe_enabled: bool = True
    earnings_enabled: bool = True
    earnings_days: int = 60
    earnings_pause_s: float = 0.5
    massive_enabled: bool = True
    massive_min_interval_s: float = 12.5
    actions_window: tuple[int, int] = (-7, 30)
    sec_enabled: bool = True
    sec_min_interval_s: float = 0.2
    sec_refresh_days: int = 30
    max_bar_count_drop: float = 0.10
    max_universe_change: float = 0.05
    min_chain_coverage: float = 0.95

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "SourcesSettings":
        doc = doc or {}

        def section(name: str) -> Mapping[str, Any]:
            value = doc.get(name, {})
            return value if isinstance(value, Mapping) else {}

        cboe, earnings, massive, quality, sec = (
            section(n) for n in ("cboe", "nasdaq_earnings", "massive", "quality", "sec_edgar")
        )
        window = massive.get("corporate_actions_window", list(cls.actions_window))
        d = cls()
        return cls(
            raw_retention_days=int(doc.get("raw_retention_days", d.raw_retention_days)),
            cboe_enabled=bool(cboe.get("enabled", True)),
            cboe_workers=int(cboe.get("workers", d.cboe_workers)),
            universe_enabled=bool(section("nasdaq_trader").get("enabled", True)),
            earnings_enabled=bool(earnings.get("enabled", True)),
            earnings_days=int(earnings.get("days", d.earnings_days)),
            earnings_pause_s=float(earnings.get("pause_s", d.earnings_pause_s)),
            massive_enabled=bool(massive.get("enabled", True)),
            massive_min_interval_s=float(massive.get("min_interval_s", d.massive_min_interval_s)),
            actions_window=(int(window[0]), int(window[1])),
            sec_enabled=bool(sec.get("enabled", True)),
            sec_min_interval_s=float(sec.get("min_interval_s", d.sec_min_interval_s)),
            sec_refresh_days=int(sec.get("refresh_days", d.sec_refresh_days)),
            max_bar_count_drop=float(quality.get("max_bar_count_drop", d.max_bar_count_drop)),
            max_universe_change=float(quality.get("max_universe_change", d.max_universe_change)),
            min_chain_coverage=float(quality.get("min_chain_coverage", d.min_chain_coverage)),
        )


def load_sources(configs: ConfigStore) -> SourcesSettings:
    return SourcesSettings.from_document(configs.load("site", "settings", "sources"))
