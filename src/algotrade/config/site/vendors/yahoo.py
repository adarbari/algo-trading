"""``sources.toml [yahoo]``: the analyst snapshot's Yahoo step, validated (ADR 0080).

Read by ``SourcesSettings.from_document`` (``config/site/settings.py``), the one loader; it lives
in its own module to keep that file under the length limit. ``licence`` is the owner-only tag
``yahoo`` (Yahoo's terms forbid scraping: personal use, never served to another viewer).
"""

from dataclasses import dataclass

from algotrade.config.site.fields import Table
from algotrade.config.site.macro import HELD_LICENCES

LICENCE = "yahoo"
YAHOO_KEYS = (
    "licence",
    "per_night",
    "refresh_days",
    "standby_days",
    "run_budget_s",
    "backfill_batch",
    "backfill_min_interval_s",
    "cache_dir",
)


@dataclass(frozen=True)
class YahooSettings:
    licence: str = LICENCE  # what its analyst data is licensed for: the owner only
    per_night: int = 360  # names asked a night (one call each, largest market cap first)
    refresh_days: int = 14  # a name FMP does not answer is asked again after this many days
    standby_days: int = 45  # a name FMP answers (the reader prefers FMP) is asked this rarely
    run_budget_s: int = 900  # its own time cap: after it no further call is made
    backfill_batch: int = 500  # names one ``analyst-backfill`` run asks (one batch, then it ends)
    backfill_min_interval_s: float = 0.3  # the backfill's pacing floor (adapts up to 3 s on errors)
    cache_dir: str = "var/cache/yahoo"  # yfinance's cookie and timezone caches


def parse_yahoo(section: Table) -> YahooSettings:
    """The typed ``[yahoo]`` keys beyond the vendor keys (``enabled``, ``min_interval_s``, ...)."""
    d = YahooSettings()
    return YahooSettings(
        licence=section.choice("licence", d.licence, HELD_LICENCES),
        per_night=section.integer("per_night", d.per_night, 0),
        refresh_days=section.integer("refresh_days", d.refresh_days, 1),
        standby_days=section.integer("standby_days", d.standby_days, 1),
        run_budget_s=section.integer("run_budget_s", d.run_budget_s, 1),
        backfill_batch=section.integer("backfill_batch", d.backfill_batch, 1),
        backfill_min_interval_s=section.number(
            "backfill_min_interval_s", d.backfill_min_interval_s, 0
        ),
        cache_dir=section.text("cache_dir", d.cache_dir),
    )
