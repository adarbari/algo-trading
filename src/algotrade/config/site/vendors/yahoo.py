"""``sources.toml [yahoo]``: the analyst snapshot's Yahoo step, validated (ADR 0080).

Read by ``SourcesSettings.from_document`` (``config/site/settings.py``), the one loader; it lives
in its own module to keep that file under the length limit. ``licence`` is the owner-only tag
``yahoo`` (Yahoo's terms forbid scraping: personal use, never served to another viewer); the
other tags are accepted so a PR that narrows it later changes only this tuple.
"""

from dataclasses import dataclass

from algotrade.config.site.fields import Table
from algotrade.config.site.macro import LICENCES

LICENCE = "yahoo"
YAHOO_KEYS = ("licence", "per_night", "refresh_days", "run_budget_s", "cache_dir")


@dataclass(frozen=True)
class YahooSettings:
    licence: str = LICENCE  # what its analyst data is licensed for: the owner only
    per_night: int = 60  # names asked a night (one call each, largest market cap first)
    refresh_days: int = 14  # an answered name is asked again after this many days
    run_budget_s: int = 600  # its own time cap: after it no further call is made
    cache_dir: str = "var/cache/yahoo"  # yfinance's cookie and timezone caches


def parse_yahoo(section: Table) -> YahooSettings:
    """The typed ``[yahoo]`` keys beyond the vendor keys (``enabled``, ``min_interval_s``, ...)."""
    d = YahooSettings()
    return YahooSettings(
        licence=section.choice("licence", d.licence, (*LICENCES, LICENCE)),
        per_night=section.integer("per_night", d.per_night, 0),
        refresh_days=section.integer("refresh_days", d.refresh_days, 1),
        run_budget_s=section.integer("run_budget_s", d.run_budget_s, 1),
        cache_dir=section.text("cache_dir", d.cache_dir),
    )
