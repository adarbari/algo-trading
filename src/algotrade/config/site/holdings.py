"""Site settings for ETF holdings (ADR 0035): ``sources.toml [etf_holdings]``, and the
``[spy_holdings]`` -> ``[ssga]`` section rename that older files still carry.

Read by ``SourcesSettings.from_document`` (``config/site/settings.py``), the one loader; it lives
in its own module to keep that file under the length limit.
"""

from dataclasses import dataclass

from algotrade.config.site.fields import Table

FALLBACK_SCOPES = ("liquid", "optionable", "all", "off")
KEYS = ("refresh_days", "keep_top", "fallback_scope", "fallback_min_adv_usd", "per_night")
OWN_KEYS_ONLY = {"etf_holdings": ("enabled",)}  # no pacing or retention of its own
VENDOR_FLAGS = {"ssga": ("etf_files",)}  # [ssga] etf_files = false: SPY membership stays on
# Sections that were renamed: a file with only the old one keeps its on/off switch under the new
# name (pacing is not inherited: the old SPY file ran unpaced, the new section paces every file).
LEGACY_SECTIONS = {"ssga": "spy_holdings"}


@dataclass(frozen=True)
class EtfHoldingsSettings:
    """``[etf_holdings]``: how the ``etf-holdings`` task and the nightly read funds."""

    refresh_days: int = 7  # refetch a fund's holdings once per window (spread by ticker)
    keep_top: int = 100  # holdings stored per fund, largest weights first (0: all)
    per_night: int = 200  # funds the nightly reads per night, new and stalest first (0: no cap)
    fallback_scope: str = (
        "liquid"  # which funds SEC N-PORT is read for: liquid, optionable, all, off
    )
    fallback_min_adv_usd: float = 5_000_000.0  # "liquid": also funds trading at least this a day

    @classmethod
    def from_table(cls, section: Table) -> "EtfHoldingsSettings":
        d = cls()
        return cls(
            refresh_days=section.integer("refresh_days", d.refresh_days, 0),
            keep_top=section.integer("keep_top", d.keep_top, 0),
            per_night=section.integer("per_night", d.per_night, 0),
            fallback_scope=section.choice("fallback_scope", d.fallback_scope, FALLBACK_SCOPES),
            fallback_min_adv_usd=section.number(
                "fallback_min_adv_usd", d.fallback_min_adv_usd, 0.0
            ),
        )
