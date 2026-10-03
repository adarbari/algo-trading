"""Typed views of ``config/site/sources.toml`` and ``universe.toml`` (L3), loaded here only.

Missing files or keys fall back to defaults.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from algotrade.storage.config_store import ConfigStore
from algotrade_ingestion.tasks.classify import DEFAULT_LEVERAGE_MARKERS


@dataclass(frozen=True)
class VendorSettings:
    """One vendor section of ``sources.toml``: on/off and its pacing (``None``: the
    registry's default for that source)."""

    enabled: bool = True
    min_interval_s: float | None = None


@dataclass(frozen=True)
class SourcesSettings:
    raw_retention_days: int = 90
    staging_retention_days: int = 14
    vendors: Mapping[str, VendorSettings] = field(default_factory=dict)  # by section name
    cboe_workers: int = 4
    earnings_days: int = 60
    actions_window: tuple[int, int] = (-7, 30)
    sec_refresh_days: int = 30
    http_max_retry_s: float = 300.0
    http_breaker_failures: int = 10
    limits_dir: str = "var/run/limits"
    max_bar_count_drop: float = 0.10
    max_universe_change: float = 0.05
    min_chain_coverage: float = 0.95

    def vendor(self, section: str) -> VendorSettings:
        """``[section]`` of sources.toml (defaults when the section is missing)."""
        return self.vendors.get(section, VendorSettings())

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "SourcesSettings":
        doc = doc or {}

        def section(name: str) -> Mapping[str, Any]:
            value = doc.get(name, {})
            return value if isinstance(value, Mapping) else {}

        cboe, earnings, massive, quality, sec, http = (
            section(n)
            for n in ("cboe", "nasdaq_earnings", "massive", "quality", "sec_edgar", "http")
        )
        window = massive.get("corporate_actions_window", list(cls.actions_window))
        d = cls()
        return cls(
            raw_retention_days=int(doc.get("raw_retention_days", d.raw_retention_days)),
            staging_retention_days=int(doc.get("staging_retention_days", d.staging_retention_days)),
            vendors={
                name: _vendor(value)
                for name, value in doc.items()
                if isinstance(value, Mapping) and name not in ("quality", "http")
            },
            cboe_workers=int(cboe.get("workers", d.cboe_workers)),
            earnings_days=int(earnings.get("days", d.earnings_days)),
            actions_window=(int(window[0]), int(window[1])),
            sec_refresh_days=int(sec.get("refresh_days", d.sec_refresh_days)),
            http_max_retry_s=float(http.get("max_retry_s", d.http_max_retry_s)),
            http_breaker_failures=int(http.get("breaker_failures", d.http_breaker_failures)),
            limits_dir=str(http.get("limits_dir", d.limits_dir)),
            max_bar_count_drop=float(quality.get("max_bar_count_drop", d.max_bar_count_drop)),
            max_universe_change=float(quality.get("max_universe_change", d.max_universe_change)),
            min_chain_coverage=float(quality.get("min_chain_coverage", d.min_chain_coverage)),
        )


def _vendor(section: Mapping[str, Any]) -> VendorSettings:
    interval = section.get("min_interval_s")
    return VendorSettings(
        enabled=bool(section.get("enabled", True)),
        min_interval_s=None if interval is None else float(interval),
    )


@dataclass(frozen=True)
class UniverseSettings:
    security_types: tuple[str, ...] = ("COMMON_STOCK", "ADR", "ETF")
    exclude_test_issues: bool = True
    include_symbols: frozenset[str] = frozenset()
    exclude_symbols: frozenset[str] = frozenset()
    leverage_markers: tuple[str, ...] = DEFAULT_LEVERAGE_MARKERS
    overrides: tuple[Mapping[str, str], ...] = field(default=())

    @classmethod
    def from_documents(
        cls, doc: Mapping[str, Any] | None, overrides: list[dict[str, str]]
    ) -> "UniverseSettings":
        doc = doc or {}
        return cls(
            security_types=tuple(doc.get("security_types", cls.security_types)),
            exclude_test_issues=bool(doc.get("exclude_test_issues", True)),
            include_symbols=frozenset(s.upper() for s in doc.get("include_symbols", [])),
            exclude_symbols=frozenset(s.upper() for s in doc.get("exclude_symbols", [])),
            leverage_markers=tuple(doc.get("leverage_markers", DEFAULT_LEVERAGE_MARKERS)),
            overrides=tuple(overrides),
        )


def site_document(configs: ConfigStore, name: str) -> Mapping[str, Any] | None:
    """``config/site/<name>.toml`` (``None`` when the file is missing)."""
    return configs.load("site", "settings", name)


def load_sources(configs: ConfigStore) -> SourcesSettings:
    return SourcesSettings.from_document(site_document(configs, "sources"))


def universe_settings(configs: ConfigStore) -> tuple[str, UniverseSettings]:
    """``config/site/universe.toml`` -> (source, settings). Missing file: CSV import mode."""
    doc = site_document(configs, "universe")
    settings = UniverseSettings.from_documents(doc, configs.overrides("leveraged_etfs"))
    return str((doc or {}).get("source", "csv_import")), settings
